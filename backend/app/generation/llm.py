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
from collections.abc import Callable
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


class AnthropicLLM:
    def __init__(self, settings: Settings) -> None:
        import anthropic

        self._anthropic = anthropic
        self.model = settings.llm_model
        self.effort = settings.llm_effort
        self.client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key, timeout=settings.llm_timeout_s, max_retries=2
        )

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
        self.effort = settings.llm_effort
        self.max_retries = settings.llm_max_retries
        self._sleep = sleep
        self.client = client or httpx.Client(
            base_url=settings.llm_base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            timeout=settings.llm_timeout_s,
        )

    @property
    def model(self) -> str:
        """The model the next turn will try first: out-of-quota models are skipped."""
        now = time.monotonic()
        return next((m for m in self.models if _EXHAUSTED.get(m, 0.0) <= now), self.models[0])

    def turn(
        self, *, system: str, messages: list, tools: list[dict], output_schema: dict
    ) -> LLMTurn:
        body: dict[str, Any] = {
            "messages": _to_openai_messages(system, messages),
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "answer", "schema": output_schema},
            },
        }
        if tools:  # an empty tools list is rejected by some providers
            body["tools"] = [_to_openai_tool(t) for t in tools]
        if self.effort:
            body["reasoning_effort"] = self.effort

        data, model = self._post_with_fallback(body)
        try:
            choice = data["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Unexpected response shape: {str(data)[:200]}") from exc

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


def get_llm(settings: Settings) -> LLM | None:
    """None when no API key is configured: the copilot then runs in offline mode."""
    if not settings.llm_enabled:
        return None
    if settings.llm_provider == "openai":
        return OpenAICompatLLM(settings)
    return AnthropicLLM(settings)
