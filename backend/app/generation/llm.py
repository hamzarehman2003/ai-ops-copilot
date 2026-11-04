"""One LLM provider (Anthropic Claude) behind a small adapter.

The copilot drives the tool loop itself (see copilot.py); the adapter only does one model
turn. That keeps the provider swappable and lets tests use a scripted fake.

Request shape (claude-opus-5-5):
- `output_config.format`: the final answer is JSON matching ANSWER_SCHEMA (structured output);
- `tools` with `strict: true`: tool inputs always match their schema;
- `output_config.effort`: thinking depth (thinking is always on for this model);
- server-side `fallbacks: "default"`: if the model declines for a safety reason, the API
  retries on a fallback model inside the same call.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.config import Settings


class LLMError(Exception):
    """The provider could not produce a turn (network, rate limit, bad request...)."""


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


def get_llm(settings: Settings) -> LLM | None:
    """None when no API key is configured: the copilot then runs in offline mode."""
    return AnthropicLLM(settings) if settings.llm_enabled else None
