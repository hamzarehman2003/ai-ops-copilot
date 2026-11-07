"""OpenAI-compatible adapter (Gemini, Ollama, Groq, OpenAI): translation, retries, and one
full copilot run through it. A mocked HTTP transport stands in for the provider."""

import json

import httpx
import pytest
from sqlalchemy import select

from app.config import Settings
from app.generation import llm as llm_module
from app.generation.copilot import ask
from app.generation.llm import AnthropicLLM, LLMError, OpenAICompatLLM, get_llm
from app.models import ActionStatus, Customer, ProposedAction, ToolCallStatus, User

SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}}
TOOL = {
    "name": "get_account_status",
    "description": "Account status",
    "strict": True,
    "input_schema": {"type": "object", "properties": {"customer_id": {"type": "string"}}},
}
SIGNATURE = {"google": {"thought_signature": "sig-123"}}


def settings(**overrides) -> Settings:
    base = dict(
        llm_provider="openai",
        llm_api_key="test-key",
        anthropic_api_key=None,
        llm_base_url="https://llm.test/v1",
        llm_model="test-model",
        llm_fallback_models="",  # pin everything .env could set
        llm_schema_with_tools=True,
        llm_temperature=None,
        llm_max_output_tokens=None,
        llm_effort="low",
        llm_max_retries=2,
        llm_timeout_s=90.0,
    )
    return Settings(**(base | overrides))


class Provider:
    """Scripted provider: each request pops the next (status, body, headers) response."""

    def __init__(self, *responses) -> None:
        self.responses = list(responses)
        self.requests: list[dict] = []
        self.sleeps: list[float] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-key"
        self.requests.append(json.loads(request.content))
        status, body, headers = self.responses.pop(0)
        return httpx.Response(status, json=body, headers=headers)

    def llm(self, **overrides) -> OpenAICompatLLM:
        client = httpx.Client(
            base_url="https://llm.test/v1",
            headers={"Authorization": "Bearer test-key"},
            transport=httpx.MockTransport(self.handler),
        )
        return OpenAICompatLLM(settings(**overrides), client=client, sleep=self.sleeps.append)


def ok(message: dict, finish_reason: str = "stop") -> tuple:
    body = {
        "model": "test-model",
        "choices": [{"index": 0, "finish_reason": finish_reason, "message": message}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }
    return 200, body, {}


def tool_call_message(call_id: str, name: str, args: dict) -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)},
                "extra_content": SIGNATURE,
            }
        ],
    }


def test_tool_call_round_trip_keeps_provider_extras():
    provider = Provider(
        ok(tool_call_message("call_1", "get_account_status", {"customer_id": "C1"}), "tool_calls"),
        ok({"role": "assistant", "content": '```json\n{"answer": "suspended"}\n```'}),
    )
    llm = provider.llm()

    question = [{"role": "user", "content": "q"}]
    first = llm.turn(system="rules", messages=question, tools=[TOOL], output_schema=SCHEMA)
    assert first.stop_reason == "tool_use"
    assert [(u.id, u.name, u.input) for u in first.tool_uses] == [
        ("call_1", "get_account_status", {"customer_id": "C1"})
    ]
    assert first.usage == {"input_tokens": 10, "output_tokens": 5}

    request = provider.requests[0]
    assert request["messages"][0] == {"role": "system", "content": "rules"}
    assert request["tools"][0]["function"]["parameters"] == TOOL["input_schema"]
    assert request["response_format"]["json_schema"]["schema"] == SCHEMA
    assert request["reasoning_effort"] == "low"

    # The copilot appends the raw assistant turn plus Anthropic-style tool_result blocks.
    messages = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": first.content},
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "call_1", "content": '{"s": 1}'},
            ],
        },
    ]
    second = llm.turn(system="rules", messages=messages, tools=[TOOL], output_schema=SCHEMA)
    assert second.stop_reason == "end_turn"
    assert json.loads(second.text) == {"answer": "suspended"}  # code fences stripped

    sent = provider.requests[1]["messages"]
    assert sent[2]["tool_calls"][0]["extra_content"] == SIGNATURE  # sent back unchanged
    assert "content" not in sent[2]  # null fields dropped
    assert sent[3] == {"role": "tool", "tool_call_id": "call_1", "content": '{"s": 1}'}


def test_no_tools_key_and_no_effort_when_unset():
    provider = Provider(ok({"role": "assistant", "content": "{}"}))
    provider.llm(llm_effort="").turn(
        system="s", messages=[{"role": "user", "content": "q"}], tools=[], output_schema=SCHEMA
    )
    assert "tools" not in provider.requests[0]
    assert "reasoning_effort" not in provider.requests[0]
    assert "temperature" not in provider.requests[0]  # provider default unless configured
    assert "max_tokens" not in provider.requests[0]


def test_temperature_and_token_cap_are_sent_when_set():
    provider = Provider(ok({"role": "assistant", "content": "{}"}))
    provider.llm(llm_temperature=0.2, llm_max_output_tokens=4096).turn(
        system="s", messages=[{"role": "user", "content": "q"}], tools=[], output_schema=SCHEMA
    )
    assert provider.requests[0]["temperature"] == 0.2
    assert provider.requests[0]["max_tokens"] == 4096


def test_rate_limit_is_retried_with_retry_after():
    provider = Provider(
        (429, {"error": {"message": "slow down"}}, {"retry-after": "3"}),
        (503, {"error": {"message": "overloaded"}}, {}),
        ok({"role": "assistant", "content": "{}"}),
    )
    turn = provider.llm().turn(
        system="s", messages=[{"role": "user", "content": "q"}], tools=[], output_schema=SCHEMA
    )
    assert turn.text == "{}"
    assert provider.sleeps == [3.0, 4.0]  # Retry-After, then exponential backoff


def test_retries_are_bounded():
    provider = Provider(*[(429, [{"error": {"message": "quota"}}], {})] * 3)
    with pytest.raises(LLMError, match="HTTP 429: quota"):
        provider.llm().turn(
            system="s", messages=[{"role": "user", "content": "q"}], tools=[], output_schema=SCHEMA
        )
    assert len(provider.requests) == 3  # 1 + llm_max_retries


def test_client_errors_are_not_retried():
    provider = Provider((400, {"error": {"message": "bad schema"}}, {}))
    with pytest.raises(LLMError, match="HTTP 400: bad schema"):
        provider.llm().turn(
            system="s", messages=[{"role": "user", "content": "q"}], tools=[], output_schema=SCHEMA
        )
    assert len(provider.requests) == 1


def test_get_llm_selects_provider():
    assert isinstance(get_llm(settings()), OpenAICompatLLM)
    assert get_llm(settings(llm_api_key=None)) is None
    anthropic = settings(llm_provider="anthropic", anthropic_api_key="sk-test")
    assert isinstance(get_llm(anthropic), AnthropicLLM)
    assert get_llm(settings(llm_provider="anthropic")) is None


def test_copilot_runs_end_to_end_through_the_adapter(indexed):
    """Same loop and checks as with Claude: tool authorized and recorded, citation kept,
    proposal stored as pending."""
    final = {
        "answer": "The workspace is suspended after failed payments [S1].",
        "citations": ["S1"],
        "abstained": False,
        "missing_information": "",
        "proposed_action": {
            "type": "add_ticket_tag",
            "ticket_id": "TCK-2041",
            "value": "billing",
            "reason": "Payment issue",
        },
    }
    provider = Provider(
        ok(
            tool_call_message("call_1", "get_account_status", {"customer_id": "CUST-1001"}),
            "tool_calls",
        ),
        ok({"role": "assistant", "content": json.dumps(final)}),
    )
    session = indexed.session
    run = ask(
        session,
        indexed.settings,
        session.scalar(select(User).where(User.email == "agent@tasklane.example")),
        "Why can't Brightpath's team create tasks or upload files?",
        customer=session.scalar(select(Customer).where(Customer.external_id == "CUST-1001")),
        llm=provider.llm(),
    )

    assert run.mode == "llm" and run.model == "test-model"
    assert run.payload.citations == ["S1"]
    assert [c.status for c in run.tool_ctx.calls] == [ToolCallStatus.OK]
    tool_message = provider.requests[1]["messages"][-1]
    assert tool_message["role"] == "tool" and "suspended" in tool_message["content"]
    assert session.get(ProposedAction, run.action_id).status == ActionStatus.PENDING


# --- Servers whose JSON-schema mode blocks tool calls (Ollama) ---------------------------------

ANSWER = {"type": "object", "required": ["answer", "citations"]}
QUESTION_ONLY = [{"role": "user", "content": "q"}]


def test_tool_turns_omit_the_schema_when_it_would_block_tool_calls():
    provider = Provider(ok(tool_call_message("call_1", "get_account_status", {}), "tool_calls"))
    turn = provider.llm(llm_schema_with_tools=False).turn(
        system="s", messages=QUESTION_ONLY, tools=[TOOL], output_schema=ANSWER
    )
    assert turn.stop_reason == "tool_use"
    assert "response_format" not in provider.requests[0]
    assert "tools" in provider.requests[0]


def test_a_free_form_answer_is_re_requested_with_the_schema():
    provider = Provider(
        ok({"role": "assistant", "content": "The workspace is suspended."}),
        ok({"role": "assistant", "content": '{"answer": "suspended", "citations": []}'}),
    )
    turn = provider.llm(llm_schema_with_tools=False).turn(
        system="s", messages=QUESTION_ONLY, tools=[TOOL], output_schema=ANSWER
    )
    assert json.loads(turn.text)["answer"] == "suspended"
    retry = provider.requests[1]
    assert retry["response_format"]["json_schema"]["schema"] == ANSWER
    assert "tools" not in retry
    assert retry["messages"] == provider.requests[0]["messages"]  # the draft is not sent back


def test_an_answer_that_already_fits_the_schema_is_kept():
    provider = Provider(ok({"role": "assistant", "content": '{"answer": "a", "citations": []}'}))
    provider.llm(llm_schema_with_tools=False).turn(
        system="s", messages=QUESTION_ONLY, tools=[TOOL], output_schema=ANSWER
    )
    assert len(provider.requests) == 1


def test_without_tools_the_schema_is_always_sent():
    provider = Provider(ok({"role": "assistant", "content": "{}"}))
    provider.llm(llm_schema_with_tools=False).turn(
        system="s", messages=QUESTION_ONLY, tools=[], output_schema=ANSWER
    )
    assert "response_format" in provider.requests[0]


# --- Tool calls the server can't parse (small local models + several tools) --------------------

TICKETS = {
    "name": "get_recent_tickets",
    "description": "Recent tickets",
    "input_schema": {"type": "object", "properties": {"customer_id": {"type": "string"}}},
}
UNPARSEABLE = (
    500,
    {"error": {"message": "expected element type <function> but have <parameter>"}},
    {},
)


def test_unparseable_tool_calls_are_retried_one_tool_at_a_time():
    provider = Provider(
        UNPARSEABLE,
        ok(tool_call_message("call_1", "get_account_status", {"customer_id": "C1"}), "tool_calls"),
    )
    turn = provider.llm().turn(
        system="s", messages=QUESTION_ONLY, tools=[TOOL, TICKETS], output_schema=SCHEMA
    )
    assert turn.tool_uses[0].name == "get_account_status"
    assert provider.sleeps == []  # not a transient error: no backoff, no same-request retry
    assert [len(r["tools"]) for r in provider.requests] == [2, 1]


def test_the_one_tool_retry_offers_tools_not_called_yet_first():
    provider = Provider(
        UNPARSEABLE,
        ok(tool_call_message("call_2", "get_recent_tickets", {"customer_id": "C1"}), "tool_calls"),
    )
    earlier = tool_call_message("call_1", "get_account_status", {"customer_id": "C1"})
    messages = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": earlier},
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "call_1", "content": "{}"}],
        },
    ]
    provider.llm().turn(system="s", messages=messages, tools=[TOOL, TICKETS], output_schema=SCHEMA)
    assert provider.requests[1]["tools"][0]["function"]["name"] == "get_recent_tickets"


def test_unparseable_with_a_single_tool_is_an_error():
    provider = Provider(UNPARSEABLE)
    with pytest.raises(LLMError, match="expected element type"):
        provider.llm().turn(system="s", messages=QUESTION_ONLY, tools=[TOOL], output_schema=SCHEMA)
    assert len(provider.requests) == 1


# --- Fallback models (free tiers have small per-model daily quotas) ----------------------------

DAILY_QUOTA = [
    {
        "error": {
            "code": 429,
            "message": "You exceeded your current quota",
            "details": [
                {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "59614s"}
            ],
        }
    }
]


@pytest.fixture(autouse=True)
def fresh_quota_state():
    llm_module._EXHAUSTED.clear()
    yield
    llm_module._EXHAUSTED.clear()


def test_daily_quota_falls_back_without_retrying_and_is_remembered():
    provider = Provider(
        (429, DAILY_QUOTA, {}),
        ok({"role": "assistant", "content": "{}"}),
        ok({"role": "assistant", "content": "{}"}),
    )
    turn = provider.llm(llm_fallback_models="lite-a, lite-b").turn(
        system="s", messages=[{"role": "user", "content": "q"}], tools=[], output_schema=SCHEMA
    )
    assert [r["model"] for r in provider.requests] == ["test-model", "lite-a"]
    assert provider.sleeps == []  # a day-long retryDelay is not worth waiting for
    assert turn.model == "test-model"  # the mock echoes a fixed name; real APIs return their own

    # The next request (a new adapter, as per HTTP request) skips the exhausted model.
    provider.llm(llm_fallback_models="lite-a, lite-b").turn(
        system="s", messages=[{"role": "user", "content": "q"}], tools=[], output_schema=SCHEMA
    )
    assert provider.requests[-1]["model"] == "lite-a"


def test_overloaded_model_falls_back_after_retries():
    provider = Provider(
        (503, {"error": {"message": "high demand"}}, {}),
        (503, {"error": {"message": "high demand"}}, {}),
        (503, {"error": {"message": "high demand"}}, {}),
        ok({"role": "assistant", "content": "{}"}),
    )
    provider.llm(llm_fallback_models="lite-a").turn(
        system="s", messages=[{"role": "user", "content": "q"}], tools=[], output_schema=SCHEMA
    )
    assert [r["model"] for r in provider.requests] == ["test-model"] * 3 + ["lite-a"]
    assert llm_module._EXHAUSTED == {}  # overload is temporary: not remembered


def test_all_models_unavailable_names_each_failure():
    provider = Provider((429, DAILY_QUOTA, {}), (429, DAILY_QUOTA, {}))
    with pytest.raises(LLMError, match="test-model: HTTP 429.*lite-a: HTTP 429"):
        provider.llm(llm_fallback_models="lite-a").turn(
            system="s", messages=[{"role": "user", "content": "q"}], tools=[], output_schema=SCHEMA
        )


def test_bad_requests_do_not_fall_back():
    provider = Provider((400, {"error": {"message": "bad schema"}}, {}))
    with pytest.raises(LLMError, match="bad schema"):
        provider.llm(llm_fallback_models="lite-a").turn(
            system="s", messages=[{"role": "user", "content": "q"}], tools=[], output_schema=SCHEMA
        )
    assert len(provider.requests) == 1


def test_model_name_skips_exhausted_models():
    llm = Provider().llm(llm_fallback_models="lite-a")
    assert llm.model == "test-model"
    llm_module._EXHAUSTED["test-model"] = float("inf")
    assert llm.model == "lite-a"  # what the progress UI shows before the turn
