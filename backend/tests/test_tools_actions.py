import pytest
from sqlalchemy import func, select

from app.config import Settings
from app.models import (
    ActionStatus,
    AuditEvent,
    Customer,
    Ticket,
    TicketNote,
    ToolCall,
    ToolCallStatus,
    User,
)
from app.seed import seed
from app.tools.actions import (
    ActionError,
    approve_action,
    execute_action,
    propose_action,
    reject_action,
)
from app.tools.crm import MockCrm
from app.tools.registry import ToolContext, run_tool


@pytest.fixture
def demo(session):
    seed(session)
    return session


def customer(session, external_id: str) -> Customer:
    return session.scalar(select(Customer).where(Customer.external_id == external_id))


def user(session, email: str) -> User:
    return session.scalar(select(User).where(User.email == email))


def context(session, allowed: Customer | None, **settings) -> ToolContext:
    return ToolContext(
        session=session,
        settings=Settings(**settings),
        workspace_id=user(session, "agent@tasklane.example").workspace_id,
        allowed_customer_id=allowed.id if allowed else None,
    )


# --- Read-only tools ------------------------------------------------------------------------


def test_account_status_for_the_selected_customer(demo):
    brightpath = customer(demo, "CUST-1001")
    outcome = run_tool(
        context(demo, brightpath), "get_account_status", {"customer_id": "CUST-1001"}
    )

    assert outcome.ok
    assert outcome.result["account_status"] == "suspended"
    record = demo.get(ToolCall, outcome.record.id)
    assert record.status == ToolCallStatus.OK and record.arguments == {"customer_id": "CUST-1001"}


@pytest.mark.parametrize(
    "requested",
    [
        "CUST-1002",  # same workspace, but not the customer the agent selected
        "CUST-9001",  # another tenant's customer
        "CUST-0000",  # does not exist
    ],
)
def test_model_cannot_choose_another_customer(demo, requested):
    ctx = context(demo, customer(demo, "CUST-1001"))
    outcome = run_tool(ctx, "get_recent_tickets", {"customer_id": requested})

    assert outcome.status == ToolCallStatus.DENIED
    assert outcome.error_code == "CUSTOMER_NOT_IN_SCOPE"
    assert outcome.result is None


def test_no_selected_customer_means_no_account_data(demo):
    outcome = run_tool(context(demo, None), "get_account_status", {"customer_id": "CUST-1001"})
    assert outcome.status == ToolCallStatus.DENIED


def test_unknown_tools_and_bad_arguments_are_refused(demo):
    ctx = context(demo, customer(demo, "CUST-1001"))
    assert run_tool(ctx, "delete_workspace", {}).error_code == "UNKNOWN_TOOL"
    bad = run_tool(ctx, "get_recent_tickets", {"customer_id": "CUST-1001", "limit": 500})
    assert bad.error_code == "INVALID_ARGUMENTS"


def test_timeouts_are_retried_then_reported(demo):
    ctx = context(demo, customer(demo, "CUST-1001"), crm_fault="timeout", crm_max_retries=2)
    outcome = run_tool(ctx, "get_account_status", {"customer_id": "CUST-1001"})

    assert outcome.status == ToolCallStatus.TIMEOUT
    assert outcome.record.attempts == 3  # 1 try + 2 retries, then give up (bounded)
    assert outcome.for_model() == '{"error": "TIMEOUT"}'


def test_malformed_crm_response_is_an_error_not_facts(demo):
    ctx = context(demo, customer(demo, "CUST-1001"), crm_fault="malformed")
    outcome = run_tool(ctx, "get_account_status", {"customer_id": "CUST-1001"})

    assert outcome.status == ToolCallStatus.ERROR
    assert outcome.error_code == "MALFORMED_RESPONSE"
    assert outcome.result is None


# --- Proposed actions -------------------------------------------------------------------------


def propose(session, **overrides):
    agent = user(session, "agent@tasklane.example")
    args = {
        "workspace_id": agent.workspace_id,
        "customer_id": customer(session, "CUST-1001").id,
        "proposed_by": agent,
        "ticket_external_id": "TCK-2041",
        "action_type": "add_ticket_note",
        "value": "Workspace suspended after failed renewal; sent payment-update link.",
        "reason": "Explains the access problem.",
    }
    return propose_action(session, **{**args, **overrides})


def notes(session) -> int:
    return session.scalar(select(func.count()).select_from(TicketNote))


def test_proposal_is_pending_and_nothing_is_written(demo):
    action = propose(demo)
    assert action.status == ActionStatus.PENDING
    assert notes(demo) == 0


@pytest.mark.parametrize(
    "overrides,message",
    [
        ({"ticket_external_id": "TCK-2050"}, "not a ticket of this customer"),  # other customer
        ({"ticket_external_id": "TCK-9101"}, "not a ticket of this customer"),  # other tenant
        ({"action_type": "upgrade_plan"}, "not allowed"),
        ({"action_type": "add_ticket_tag", "value": "Not A Tag!"}, "Tag must be"),
        ({"action_type": "set_ticket_status", "value": "deleted"}, "Status must be"),
        ({"customer_id": None}, "Select a customer"),
    ],
)
def test_invalid_proposals_are_refused(demo, overrides, message):
    with pytest.raises(ActionError, match=message):
        propose(demo, **overrides)


def test_approval_executes_once_and_is_audited(demo):
    action = propose(demo)
    approver = user(demo, "agent@tasklane.example")

    approve_action(demo, action, approver, MockCrm(demo, Settings()))

    assert action.status == ActionStatus.EXECUTED
    assert action.decided_by == approver.id
    assert notes(demo) == 1
    events = demo.scalars(
        select(AuditEvent.event_type)
        .where(AuditEvent.entity_id == str(action.id))
        .order_by(AuditEvent.created_at)
    ).all()
    assert events == ["action.proposed", "action.approved", "action.executed"]

    # A retry with the same idempotency key (e.g. after a lost response) writes nothing new.
    replay = MockCrm(demo, Settings()).apply(
        action.workspace_id,
        action.ticket_id,
        action.action_type,
        action.payload,
        "retry",
        action.idempotency_key,
    )
    assert replay["replayed"] is True
    assert notes(demo) == 1


def test_approval_with_edit_uses_the_edited_value(demo):
    action = propose(demo, action_type="add_ticket_tag", value="billing")
    approve_action(
        demo,
        action,
        user(demo, "agent@tasklane.example"),
        MockCrm(demo, Settings()),
        edited_value="payment-failed",
    )
    ticket = demo.scalar(select(Ticket).where(Ticket.external_id == "TCK-2041"))
    assert "payment-failed" in ticket.tags and "billing" not in ticket.tags


def test_decisions_are_final(demo):
    action = propose(demo)
    reject_action(demo, action, user(demo, "agent@tasklane.example"), note="Not needed")
    with pytest.raises(ActionError, match="already rejected"):
        approve_action(
            demo, action, user(demo, "agent@tasklane.example"), MockCrm(demo, Settings())
        )
    assert notes(demo) == 0


def test_executor_refuses_unapproved_actions(demo):
    action = propose(demo)
    with pytest.raises(ActionError, match="Only approved"):
        execute_action(
            demo, action, user(demo, "agent@tasklane.example"), MockCrm(demo, Settings())
        )
    assert notes(demo) == 0


def test_crm_failure_marks_action_failed(demo):
    action = propose(demo)
    crm = MockCrm(demo, Settings(crm_fault="error", crm_max_retries=1))
    approve_action(demo, action, user(demo, "agent@tasklane.example"), crm)

    assert action.status == ActionStatus.FAILED
    assert action.error.startswith("UNAVAILABLE")
    assert notes(demo) == 0
