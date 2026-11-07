"""LLM providers behind a small adapter: Anthropic Claude, or any OpenAI-compatible API.

The copilot drives the tool loop itself (see copilot.py); the adapter only does one model
turn. That keeps the provider swappable and lets tests use a scripted fake. The copilot speaks
Anthropic's message shape (content blocks, `tool_result` blocks in a user turn);
`OpenAICompatLLM` translates that to Chat Completions and back, so the loop and every
grounding/authorization check are identical whichever model answers.

Anthropic request shape (claude-opus-5-5):
- `output_config.format`: the final answer is JSON matching ANSWER_SCHEMA (structured output);
- `tools` with `strict: true`: tool inputs always match their schema;
- `output_config.effort`: thinking depth (thinking is always on for this model);
- server-side `fallbacks: "default"`: if the model declines for a safety reason, the API
  retries on a fallback model inside the same call.
"""

import json
import re
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.config import Settings


class LLMError(Exception):
    """The provider could not produce a turn (network, rate limit, bad request...)."""


class ModelUnavailable(LLMError):
    """Rate-limited, out of quota, or overloaded: another model may still work."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ToolCallFormatError(LLMError):
    """The server couldn't parse the tool call(s) the model generated (Ollama returns a 500)."""


PROBE_MAX_TOKENS = 256  # tool-or-answer probe on servers without schema + tools (see _complete)

# Ollama's tool-call parser errors, e.g. "expected element type <function> but have <parameter>"
TOOL_FORMAT_ERROR = re.compile(r"expected element type|tool call|parse tool", re.IGNORECASE)

# Models whose quota ran out, until when (time.monotonic()). Process-wide because a new
# adapter is created per request; skipping them avoids a wasted call on every question.
_EXHAUSTED: dict[str, float] = {}
QUOTA_DELAY_S = 30.0  # a 429 asking to wait longer than this is a quota, not a burst


@dataclass
class ToolUse:
    id: str
    name: str
    input: dict


@dataclass
class LLMTurn:
    stop_reason: str  # end_turn | tool_use | pause_turn | max_tokens | refusal
    text: str
    tool_uses: list[ToolUse]
    content: Any  # raw content blocks, appended back unchanged on the next turn
    model: str
    usage: dict = field(default_factory=dict)


class LLM(Protocol):
    model: str

    def turn(
        self, *, system: str, messages: list, tools: list[dict], output_schema: dict
    ) -> LLMTurn: ...

    def close(self) -> None: ...  # release the HTTP connection pool


class AnthropicLLM:
    def __init__(self, settings: Settings) -> None:
        import anthropic

        self._anthropic = anthropic
        self.model = settings.llm_model
        self.effort = settings.llm_effort
        self.client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key, timeout=settings.llm_timeout_s, max_retries=2
        )

    def close(self) -> None:
        self.client.close()

    def turn(
        self, *, system: str, messages: list, tools: list[dict], output_schema: dict
    ) -> LLMTurn:
        try:
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=16000,
                system=system,
                messages=messages,
                tools=tools,
                output_config={
                    "effort": self.effort,
                    "format": {"type": "json_schema", "schema": output_schema},
                },
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except self._anthropic.APIError as exc:  # status errors, timeouts, connection errors
            raise LLMError(f"{type(exc).__name__}: {exc}") from exc

        return LLMTurn(
            stop_reason=response.stop_reason or "end_turn",
            text="".join(b.text for b in response.content if b.type == "text"),
            tool_uses=[
                ToolUse(b.id, b.name, dict(b.input))
                for b in response.content
                if b.type == "tool_use"
            ],
            content=response.content,
            model=response.model,
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
        )


class OpenAICompatLLM:
    """Any OpenAI-compatible Chat Completions endpoint: Gemini (generativelanguage.googleapis
    .com/v1beta/openai), Ollama (localhost:11434/v1), Groq, OpenAI...

    Translation, per turn:
    - system prompt -> a "system" message; tools -> {"type": "function", ...};
    - the answer schema -> response_format json_schema (structured output);
    - assistant turns are stored as the provider's raw message dict and sent back unchanged,
      which keeps provider extras such as Gemini's tool-call `thought_signature` intact;
    - Anthropic `tool_result` blocks -> one "tool" message per result.

    `llm_schema_with_tools=false` (Ollama): a JSON schema there constrains decoding so the
    model cannot emit a tool call, so tool turns are sent without it; a free-form final answer
    that does not already fit the schema is re-requested once with the schema and no tools.

    Fallback: if the model is out of quota or still overloaded after retries, the same turn is
    sent to the next of `llm_fallback_models`. Out-of-quota models are skipped until reset.
    """

    STOP_REASONS = {
        "stop": "end_turn",
        "tool_calls": "tool_use",
        "function_call": "tool_use",
        "length": "max_tokens",
        "content_filter": "refusal",
    }

    def __init__(
        self,
        settings: Settings,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        fallbacks = [m.strip() for m in settings.llm_fallback_models.split(",") if m.strip()]
        self.models = list(dict.fromkeys([settings.llm_model, *fallbacks]))
        self.schema_with_tools = settings.llm_schema_with_tools
        self.sampling = {
            key: value
            for key, value in (
                ("temperature", settings.llm_temperature),
                ("max_tokens", settings.llm_max_output_tokens),
            )
            if value is not None
        }
        self.effort = settings.llm_effort
        self.max_retries = settings.llm_max_retries
        self._sleep = sleep
        self.client = client or httpx.Client(
            base_url=settings.llm_base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            timeout=settings.llm_timeout_s,
        )

    def close(self) -> None:
        self.client.close()

    @property
    def model(self) -> str:
        """The model the next turn will try first: out-of-quota models are skipped."""
        now = time.monotonic()
        return next((m for m in self.models if _EXHAUSTED.get(m, 0.0) <= now), self.models[0])

    def turn(
        self, *, system: str, messages: list, tools: list[dict], output_schema: dict
    ) -> LLMTurn:
        body: dict[str, Any] = {"messages": _to_openai_messages(system, messages), **self.sampling}
        if self.effort:
            body["reasoning_effort"] = self.effort
        structured = {
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "answer", "schema": output_schema},
            }
        }
        if not self.schema_with_tools and tools:
            used = _called_tools(messages)
            if all(t["name"] in used for t in tools):
                # Every tool has been called: nothing left to call, so skip the free-form probe
                # (it would write a full answer only to be regenerated with the schema).
                tools = []
        try:
            data, model = self._complete(body, structured, tools, output_schema)
        except ToolCallFormatError:
            # Small local models (qwen3.5:9b on Ollama) can't emit two tool calls in one turn
            # in a format their server parses. Offer the tools one at a time, unused ones first;
            # the copilot loop then simply gets them over consecutive rounds.
            if len(tools) < 2:
                raise
            used = _called_tools(messages)
            for tool in sorted(tools, key=lambda t: t["name"] in used):
                try:
                    data, model = self._complete(body, structured, [tool], output_schema)
                    break
                except ToolCallFormatError:
                    continue
            else:
                raise
        return self._to_turn(data, model)

    def _complete(
        self, body: dict, structured: dict, tools: list[dict], output_schema: dict
    ) -> tuple[dict, str]:
        # An empty tools list is rejected by some providers, so "tools" is only sent when set.
        openai_tools = {"tools": [_to_openai_tool(t) for t in tools]} if tools else {}
        if tools and not self.schema_with_tools:
            # The schema would block tool calls: let the model choose freely first. If it
            # answered instead of calling a tool, keep that answer when it already fits the
            # schema, otherwise ask again with the schema enforced (and no tools). The probe is
            # capped: a tool call fits easily, and a text answer is cut short instead of being
            # written in full only to be thrown away.
            probe = body | openai_tools | {"max_tokens": PROBE_MAX_TOKENS}
            data, model = self._post_with_fallback(probe)
            message = _first_message(data)
            if not message.get("tool_calls") and not _fits(message.get("content"), output_schema):
                data, model = self._post_with_fallback(body | structured)
            return data, model
        return self._post_with_fallback(body | structured | openai_tools)

    def _to_turn(self, data: dict, model: str) -> LLMTurn:
        message = _first_message(data)
        choice = data["choices"][0]
        tool_uses = [_tool_use(call) for call in message.get("tool_calls") or []]
        stop_reason = self.STOP_REASONS.get(choice.get("finish_reason") or "stop", "end_turn")
        if tool_uses:
            stop_reason = "tool_use"
        usage = data.get("usage") or {}
        return LLMTurn(
            stop_reason=stop_reason,
            text=_strip_fences(message.get("content") or ""),
            tool_uses=tool_uses,
            content={k: v for k, v in message.items() if v is not None},
            model=data.get("model") or model,
            usage={
                "input_tokens": usage.get("prompt_tokens"),
                "output_tokens": usage.get("completion_tokens"),
            },
        )

    def _post_with_fallback(self, body: dict) -> tuple[dict, str]:
        errors = []
        for model in self.models:
            if _EXHAUSTED.get(model, 0.0) > time.monotonic():
                errors.append(f"{model}: out of quota")
                continue
            try:
                return self._post({"model": model, **body}), model
            except ModelUnavailable as exc:
                if exc.retry_after is not None and exc.retry_after > QUOTA_DELAY_S:
                    _EXHAUSTED[model] = time.monotonic() + exc.retry_after
                errors.append(f"{model}: {exc}")
        raise LLMError("; ".join(errors))

    def _post(self, body: dict) -> dict:
        """Bounded retries for rate limits, server errors and dropped connections. Timeouts are
        not retried: the user is waiting, and the copilot falls back to offline evidence. A 429
        that asks to wait longer than QUOTA_DELAY_S (a daily quota) is not retried either."""
        for attempt in range(self.max_retries + 1):
            last = attempt == self.max_retries
            try:
                response = self.client.post("/chat/completions", json=body)
            except httpx.TimeoutException as exc:
                raise LLMError(f"Timeout after {self.client.timeout.read}s") from exc
            except httpx.HTTPError as exc:
                if last:
                    raise ModelUnavailable(f"{type(exc).__name__}: {exc}") from exc
                self._sleep(_backoff(attempt))
                continue
            if response.status_code >= 500 and TOOL_FORMAT_ERROR.search(response.text):
                # Not transient: the same prompt produces the same unparseable tool call.
                raise ToolCallFormatError(f"HTTP {response.status_code}: {_error_text(response)}")
            if response.status_code == 429 or response.status_code >= 500:
                delay = _retry_after(response)
                message = f"HTTP {response.status_code}: {_error_text(response)}"
                if last or (delay is not None and delay > QUOTA_DELAY_S):
                    raise ModelUnavailable(message, retry_after=delay)
                self._sleep(delay if delay is not None else _backoff(attempt))
                continue
            if response.status_code >= 400:
                raise LLMError(f"HTTP {response.status_code}: {_error_text(response)}")
            try:
                return response.json()
            except ValueError as exc:
                raise LLMError("Response was not JSON") from exc
        raise LLMError("unreachable")  # pragma: no cover


def _to_openai_tool(tool: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": tool["input_schema"],
        },
    }


def _to_openai_messages(system: str, messages: list) -> list[dict]:
    out: list[dict] = [{"role": "system", "content": system}]
    for message in messages:
        content = message["content"]
        if isinstance(content, str):  # plain turns (question, conversation history)
            out.append({"role": message["role"], "content": content})
        elif isinstance(content, dict):  # an assistant turn this adapter returned earlier
            out.append(content)
        else:  # Anthropic content blocks
            for block in content:
                kind = block.get("type") if isinstance(block, dict) else None
                if kind == "tool_result":
                    out.append(
                        {
                            "role": "tool",
                            "tool_call_id": block["tool_use_id"],
                            "content": block["content"],
                        }
                    )
                elif kind == "text":
                    out.append({"role": message["role"], "content": block["text"]})
                else:
                    raise LLMError(f"Cannot translate content block {kind!r}")
    return out


def _first_message(data: dict) -> dict:
    try:
        message = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"Unexpected response shape: {str(data)[:200]}") from exc
    if not isinstance(message, dict):
        raise LLMError(f"Unexpected response shape: {str(data)[:200]}")
    return message


def _fits(content: str | None, schema: dict) -> bool:
    """Cheap check that a free-form reply is already the JSON answer: an object with every
    required top-level key. The copilot still validates it fully."""
    try:
        value = json.loads(_strip_fences(content or ""))
    except json.JSONDecodeError:
        return False
    return isinstance(value, dict) and all(key in value for key in schema.get("required", []))


def _called_tools(messages: list) -> set[str]:
    """Names of the tools already called in this conversation (either message shape)."""
    names: set[str] = set()
    for message in messages:
        content = message["content"]
        if isinstance(content, dict):  # an OpenAI-style assistant turn returned earlier
            for call in content.get("tool_calls") or []:
                names.add((call.get("function") or {}).get("name", ""))
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    names.add(block.get("name", ""))
    return names


def _tool_use(call: dict) -> ToolUse:
    function = call.get("function") or {}
    try:
        arguments = json.loads(function.get("arguments") or "{}")
    except json.JSONDecodeError:
        arguments = {}  # the tool registry rejects it and tells the model
    if not isinstance(arguments, dict):
        arguments = {}
    return ToolUse(call.get("id") or "", function.get("name") or "", arguments)


def _strip_fences(text: str) -> str:
    """Some models wrap JSON in ```json fences even with a response_format."""
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        stripped = stripped[3:-3]
        if stripped.startswith("json"):
            stripped = stripped[4:]
        return stripped.strip()
    return text


RETRY_DELAY = re.compile(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"')  # Gemini's error details


def _retry_after(response: httpx.Response) -> float | None:
    """Seconds the provider asks us to wait: Retry-After header, or Gemini's retryDelay."""
    try:
        return float(response.headers.get("retry-after", ""))
    except ValueError:
        match = RETRY_DELAY.search(response.text)
        return float(match.group(1)) if match else None


def _backoff(attempt: int) -> float:
    return min(2.0 * 2**attempt, 30.0)


def _error_text(response: httpx.Response) -> str:
    try:
        data = response.json()
        if isinstance(data, list):  # Gemini wraps errors in a list
            data = data[0]
        return str(data.get("error", {}).get("message") or data)[:200]
    except (ValueError, AttributeError, IndexError):
        return response.text[:200]


@contextmanager
def open_llm(settings: Settings) -> Iterator[LLM | None]:
    """`get_llm` for one request; closes the client's connection pool afterwards."""
    llm = get_llm(settings)
    try:
        yield llm
    finally:
        if llm is not None:
            llm.close()


def get_llm(settings: Settings) -> LLM | None:
    """None when no API key is configured: the copilot then runs in offline mode."""
    if not settings.llm_enabled:
        return None
    if settings.llm_provider == "openai":
        return OpenAICompatLLM(settings)
    return AnthropicLLM(settings)
