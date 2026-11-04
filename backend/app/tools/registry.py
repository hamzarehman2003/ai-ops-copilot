"""Read-only tools the LLM may call, and the guard rails around every call.

The model only *requests* a tool; this code decides. For each call:
1. allow-list: unknown tool names are denied;
2. argument validation (Pydantic, plus `strict: true` schemas on the API side);
3. authorization: the customer must be the one the human selected for this conversation and
   belong to the caller's workspace. A customer ID chosen by the model is never trusted;
4. timeout + bounded retries with backoff for transient errors (timeouts, 503s);
5. response validation: a malformed CRM answer becomes an error, never "facts";
6. every attempt is recorded in `tool_calls` (name, arguments, status, latency, error code).
"""

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Customer, ToolCall, ToolCallStatus
from app.tools.crm import CrmError, MockCrm

# --- Argument and response schemas --------------------------------------------------------


class CustomerArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_id: str = Field(description="Customer ID, e.g. CUST-1001")


class TicketsArgs(CustomerArgs):
    limit: int = Field(default=5, ge=1, le=10)


class AccountStatus(BaseModel):
    customer_id: str
    name: str
    plan: str
    account_status: str
    seats_paid: int
    seats_used: int
    sso_enabled: bool
    renewal_date: str | None
    billing_note: str | None


class TicketSummary(BaseModel):
    ticket_id: str
    subject: str
    status: str
    priority: str
    tags: list[str]
    created_at: str
    body: str


@dataclass
class ToolSpec:
    name: str
    description: str
    args_model: type[BaseModel]
    run: Callable[["ToolContext", BaseModel, Customer], dict]

    def api_definition(self) -> dict:
        """Tool definition for the Messages API (strict: inputs always match the schema)."""
        schema = self.args_model.model_json_schema()
        properties = {
            name: {k: v for k, v in prop.items() if k in ("type", "description")}
            for name, prop in schema["properties"].items()
        }
        return {
            "name": self.name,
            "description": self.description,
            "strict": True,
            "input_schema": {
                "type": "object",
                "properties": properties,
                "required": list(properties),
                "additionalProperties": False,
            },
        }


@dataclass
class ToolContext:
    session: Session
    settings: Settings
    workspace_id: uuid.UUID
    allowed_customer_id: uuid.UUID | None  # chosen by the human in the UI, checked server-side
    message_id: uuid.UUID | None = None
    crm: MockCrm | None = None
    calls: list[ToolCall] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.crm = self.crm or MockCrm(self.session, self.settings)


@dataclass
class ToolOutcome:
    status: ToolCallStatus
    result: dict | None
    error_code: str | None
    record: ToolCall

    @property
    def ok(self) -> bool:
        return self.status == ToolCallStatus.OK

    def for_model(self) -> str:
        """What the LLM sees: data on success, a short error code otherwise."""
        import json

        if self.ok:
            return json.dumps(self.result)
        return json.dumps({"error": self.error_code})


def _get_account_status(ctx: ToolContext, args: CustomerArgs, customer: Customer) -> dict:
    data = ctx.crm.get_account(ctx.workspace_id, customer.id)
    return AccountStatus.model_validate(data).model_dump()


def _get_recent_tickets(ctx: ToolContext, args: TicketsArgs, customer: Customer) -> dict:
    data = ctx.crm.list_tickets(ctx.workspace_id, customer.id, args.limit)
    return {"tickets": [TicketSummary.model_validate(t).model_dump() for t in data]}


READ_TOOLS: dict[str, ToolSpec] = {
    spec.name: spec
    for spec in [
        ToolSpec(
            "get_account_status",
            "Current account facts for the selected customer from the CRM: plan, account "
            "status (active, trialing, past_due, suspended, cancelled, locked), seats, SSO, "
            "renewal date, billing note. Use for any question about this customer's account.",
            CustomerArgs,
            _get_account_status,
        ),
        ToolSpec(
            "get_recent_tickets",
            "The selected customer's most recent support tickets (newest first), with status, "
            "tags, and the customer's message.",
            TicketsArgs,
            _get_recent_tickets,
        ),
    ]
}


def run_tool(ctx: ToolContext, name: str, arguments: dict) -> ToolOutcome:
    started = time.perf_counter()
    attempts = 0
    status, result, error_code = ToolCallStatus.ERROR, None, None

    spec = READ_TOOLS.get(name)
    if spec is None:
        status, error_code = ToolCallStatus.DENIED, "UNKNOWN_TOOL"
    else:
        try:
            args = spec.args_model.model_validate(arguments)
        except ValidationError:
            args, error_code = None, "INVALID_ARGUMENTS"

        customer = _authorize(ctx, args.customer_id) if args else None
        if args and customer is None:
            status, error_code = ToolCallStatus.DENIED, "CUSTOMER_NOT_IN_SCOPE"
        elif args:
            status, result, error_code, attempts = _call_with_retries(ctx, spec, args, customer)

    record = ToolCall(
        workspace_id=ctx.workspace_id,
        message_id=ctx.message_id,
        tool_name=name,
        arguments=arguments,
        status=status,
        result=result,
        error_code=error_code,
        attempts=max(attempts, 1),
        latency_ms=int((time.perf_counter() - started) * 1000),
    )
    ctx.session.add(record)
    ctx.session.flush()
    ctx.calls.append(record)
    return ToolOutcome(status, result, error_code, record)


def _authorize(ctx: ToolContext, external_id: str) -> Customer | None:
    if ctx.allowed_customer_id is None:
        return None
    return ctx.session.scalar(
        select(Customer).where(
            Customer.external_id == external_id,
            Customer.id == ctx.allowed_customer_id,
            Customer.workspace_id == ctx.workspace_id,
        )
    )


def _call_with_retries(ctx: ToolContext, spec: ToolSpec, args: BaseModel, customer: Customer):
    max_attempts = ctx.settings.crm_max_retries + 1
    for attempt in range(1, max_attempts + 1):
        try:
            return ToolCallStatus.OK, spec.run(ctx, args, customer), None, attempt
        except ValidationError:
            return ToolCallStatus.ERROR, None, "MALFORMED_RESPONSE", attempt
        except CrmError as exc:
            if not exc.retryable or attempt == max_attempts:
                status = ToolCallStatus.TIMEOUT if exc.code == "TIMEOUT" else ToolCallStatus.ERROR
                return status, None, exc.code, attempt
            time.sleep(0.05 * 2 ** (attempt - 1))  # exponential backoff (short: it's a mock)
    raise AssertionError("unreachable")
