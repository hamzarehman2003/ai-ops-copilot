"""Proposed write actions: propose -> (human) approve or reject -> execute.

The LLM can only *propose*. A proposal is validated here (allow-listed type, payload rules,
the ticket must belong to the conversation's customer in the caller's workspace) and stored
as `pending`. Execution happens only through `approve_action`, which records the approver
first; `execute_action` itself refuses anything not approved (CLAUDE.md rule 4).
Every step writes an audit event.
"""

import logging
import re
import time
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ActionStatus, AuditEvent, ProposedAction, Ticket, User
from app.tools.crm import CrmError, MockCrm

logger = logging.getLogger(__name__)
TAG = re.compile(r"^[a-z0-9][a-z0-9_-]{1,39}$")
TICKET_STATUSES = {"open", "pending", "solved"}
ACTION_TYPES = ("add_ticket_note", "add_ticket_tag", "set_ticket_status")


class ActionError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def build_payload(action_type: str, value: str) -> dict:
    """Validate a proposed/edited value for an action type; raises ActionError(422)."""
    value = (value or "").strip()
    if action_type == "add_ticket_note":
        if not 1 <= len(value) <= 2000:
            raise ActionError(422, "Note must be 1-2000 characters")
        return {"note": value}
    if action_type == "add_ticket_tag":
        if not TAG.match(value):
            raise ActionError(422, "Tag must be lowercase letters, digits, - or _ (2-40 chars)")
        return {"tag": value}
    if action_type == "set_ticket_status":
        if value not in TICKET_STATUSES:
            raise ActionError(422, f"Status must be one of {sorted(TICKET_STATUSES)}")
        return {"status": value}
    raise ActionError(422, f"Action type {action_type!r} is not allowed")


PAYLOAD_FIELD = {"add_ticket_note": "note", "add_ticket_tag": "tag", "set_ticket_status": "status"}


def payload_value(action_type: str, payload: dict) -> str:
    """The single editable value of a payload (what the UI shows in its edit box)."""
    return payload.get(PAYLOAD_FIELD.get(action_type, ""), "")


def propose_action(
    session: Session,
    *,
    workspace_id: uuid.UUID,
    customer_id: uuid.UUID | None,
    proposed_by: User,
    ticket_external_id: str,
    action_type: str,
    value: str,
    reason: str = "",
    message_id: uuid.UUID | None = None,
) -> ProposedAction:
    if customer_id is None:
        raise ActionError(422, "Select a customer before proposing ticket actions")
    payload = build_payload(action_type, value)
    ticket = session.scalar(
        select(Ticket).where(
            Ticket.external_id == ticket_external_id,
            Ticket.workspace_id == workspace_id,
            Ticket.customer_id == customer_id,  # only the conversation's customer's tickets
        )
    )
    if ticket is None:
        raise ActionError(422, f"Ticket {ticket_external_id} is not a ticket of this customer")

    action = ProposedAction(
        workspace_id=workspace_id,
        message_id=message_id,
        customer_id=customer_id,
        ticket_id=ticket.id,
        action_type=action_type,
        payload=payload,
        reason=reason[:1000],
        proposed_by=proposed_by.id,
        idempotency_key=f"act-{uuid.uuid4().hex}",
    )
    session.add(action)
    session.flush()
    _audit(session, action, proposed_by, "action.proposed", {"payload": payload})
    return action


def get_action_for_update(
    session: Session, workspace_id: uuid.UUID, action_id: uuid.UUID
) -> ProposedAction:
    action = session.scalar(
        select(ProposedAction)
        .where(ProposedAction.id == action_id, ProposedAction.workspace_id == workspace_id)
        .with_for_update()  # two approvers clicking at once: the second one waits, then sees 409
    )
    if action is None:
        raise ActionError(404, "Action not found")
    return action


def approve_action(
    session: Session,
    action: ProposedAction,
    approver: User,
    crm: MockCrm,
    edited_value: str | None = None,
    note: str | None = None,
) -> ProposedAction:
    if action.status != ActionStatus.PENDING:
        raise ActionError(409, f"Action is already {action.status.value}")
    final_payload = (
        build_payload(action.action_type, edited_value)
        if edited_value is not None
        else action.payload
    )
    action.final_payload = final_payload
    action.status = ActionStatus.APPROVED
    action.decided_by = approver.id
    action.decided_at = datetime.now(UTC)
    action.decision_note = note
    _audit(
        session,
        action,
        approver,
        "action.approved",
        {"edited": final_payload != action.payload, "final_payload": final_payload},
    )
    session.commit()  # the approval is durable even if execution fails next
    return execute_action(session, action, approver, crm)


def reject_action(
    session: Session, action: ProposedAction, approver: User, note: str | None = None
) -> ProposedAction:
    if action.status != ActionStatus.PENDING:
        raise ActionError(409, f"Action is already {action.status.value}")
    action.status = ActionStatus.REJECTED
    action.decided_by = approver.id
    action.decided_at = datetime.now(UTC)
    action.decision_note = note
    _audit(session, action, approver, "action.rejected", {"note": note})
    session.commit()
    return action


def retry_action(
    session: Session, action: ProposedAction, actor: User, crm: MockCrm
) -> ProposedAction:
    """Run an approved action again: after a failure, or when it is stuck in `approved`
    (the process died between approval and execution). Safe to repeat: the CRM write uses the
    action's idempotency key, so a write that already landed is replayed, not applied twice.
    The original approval stands; a retry is not a new decision."""
    if action.status not in (ActionStatus.FAILED, ActionStatus.APPROVED):
        raise ActionError(409, f"Only failed or unexecuted approved actions can be retried "
                          f"(this one is {action.status.value})")  # fmt: skip
    previous_error = action.error
    action.status = ActionStatus.APPROVED
    action.error = None
    _audit(session, action, actor, "action.retried", {"previous_error": previous_error})
    session.commit()
    return execute_action(session, action, actor, crm)


def execute_action(
    session: Session, action: ProposedAction, actor: User, crm: MockCrm
) -> ProposedAction:
    # The server-side gate: no approved record, no write. Never trust a caller to check.
    if action.status != ActionStatus.APPROVED or action.decided_by is None:
        raise ActionError(409, "Only approved actions can be executed")

    attempts = 0
    while True:
        attempts += 1
        try:
            result = crm.apply(
                action.workspace_id,
                action.ticket_id,
                action.action_type,
                action.final_payload or action.payload,
                author=f"{actor.name} (approved copilot action)",
                idempotency_key=action.idempotency_key,  # safe to retry: applied at most once
            )
        except CrmError as exc:
            if exc.retryable and attempts <= crm.max_retries:
                time.sleep(0.05 * 2 ** (attempts - 1))
                continue
            action.status = ActionStatus.FAILED
            action.error = f"{exc.code}: {exc}"
            _audit(session, action, actor, "action.failed", {"error": action.error})
            break
        except Exception as exc:  # a bug or a lost DB connection: never leave it stuck APPROVED
            logger.exception("Executing action %s failed unexpectedly", action.id)
            session.rollback()  # drop any half-applied write; the approval is already committed
            action.status = ActionStatus.FAILED
            action.error = f"UNEXPECTED: {type(exc).__name__}"
            _audit(session, action, actor, "action.failed", {"error": action.error})
            break
        else:
            action.status = ActionStatus.EXECUTED
            action.result = result
            _audit(session, action, actor, "action.executed", {"result": result})
            break
    session.commit()
    return action


def _audit(session: Session, action: ProposedAction, actor: User, event: str, data: dict) -> None:
    session.add(
        AuditEvent(
            workspace_id=action.workspace_id,
            actor_user_id=actor.id,
            event_type=event,
            entity_type="proposed_action",
            entity_id=str(action.id),
            data={"action_type": action.action_type, **data},
        )
    )
