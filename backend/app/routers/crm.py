"""Customers and tickets (mock CRM), proposed actions (approval queue), and the audit log."""

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.deps import ApproverUser, SessionDep, SettingsDep, WorkspaceDep
from app.models import ActionStatus, AuditEvent, Customer, ProposedAction, Ticket, User
from app.schemas import (
    ActionOut,
    AuditEventOut,
    CustomerOut,
    DecisionIn,
    TicketOut,
)
from app.tools.actions import (
    ActionError,
    approve_action,
    get_action_for_update,
    payload_value,
    reject_action,
)
from app.tools.crm import MockCrm

router = APIRouter(prefix="/api", tags=["crm"])


@router.get("/customers")
def list_customers(workspace: WorkspaceDep, session: SessionDep) -> list[CustomerOut]:
    customers = session.scalars(
        select(Customer).where(Customer.workspace_id == workspace.id).order_by(Customer.name)
    )
    return [CustomerOut.model_validate(c) for c in customers]


@router.get("/customers/{customer_id}/tickets")
def customer_tickets(
    customer_id: uuid.UUID, workspace: WorkspaceDep, session: SessionDep
) -> list[TicketOut]:
    customer = session.scalar(
        select(Customer).where(Customer.id == customer_id, Customer.workspace_id == workspace.id)
    )
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    tickets = session.scalars(
        select(Ticket)
        .where(Ticket.customer_id == customer.id, Ticket.workspace_id == workspace.id)
        .order_by(Ticket.created_at.desc())
    )
    return [TicketOut.model_validate(t) for t in tickets]


@router.get("/actions")
def list_actions(
    workspace: WorkspaceDep,
    session: SessionDep,
    status_filter: Annotated[ActionStatus | None, Query(alias="status")] = None,
) -> list[ActionOut]:
    query = (
        select(ProposedAction)
        .where(ProposedAction.workspace_id == workspace.id)
        .options(selectinload(ProposedAction.ticket), selectinload(ProposedAction.customer))
        .order_by(ProposedAction.created_at.desc())
        .limit(200)
    )
    if status_filter is not None:
        query = query.where(ProposedAction.status == status_filter)
    return [_action_out(a) for a in session.scalars(query)]


@router.post("/actions/{action_id}/approve")
def approve(
    action_id: uuid.UUID,
    body: DecisionIn,
    approver: ApproverUser,
    session: SessionDep,
    settings: SettingsDep,
) -> ActionOut:
    """Approve (optionally with an edited value) and execute against the mock CRM."""
    try:
        action = get_action_for_update(session, approver.workspace_id, action_id)
        action = approve_action(
            session,
            action,
            approver,
            MockCrm(session, settings),
            edited_value=body.edited_value,
            note=body.note,
        )
    except ActionError as exc:
        session.rollback()
        raise HTTPException(exc.status_code, exc.detail) from exc
    return _action_out(action)


@router.post("/actions/{action_id}/reject")
def reject(
    action_id: uuid.UUID, body: DecisionIn, approver: ApproverUser, session: SessionDep
) -> ActionOut:
    try:
        action = get_action_for_update(session, approver.workspace_id, action_id)
        action = reject_action(session, action, approver, note=body.note)
    except ActionError as exc:
        session.rollback()
        raise HTTPException(exc.status_code, exc.detail) from exc
    return _action_out(action)


@router.get("/audit-events")
def audit_events(
    workspace: WorkspaceDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[AuditEventOut]:
    rows = session.execute(
        select(AuditEvent, User.name)
        .outerjoin(User, User.id == AuditEvent.actor_user_id)
        .where(AuditEvent.workspace_id == workspace.id)
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
    )
    return [
        AuditEventOut.model_validate(event).model_copy(update={"actor_name": name})
        for event, name in rows
    ]


def _action_out(action: ProposedAction) -> ActionOut:
    return ActionOut(
        id=action.id,
        action_type=action.action_type,
        status=action.status,
        customer=f"{action.customer.external_id} {action.customer.name}",
        ticket=action.ticket.external_id,
        ticket_subject=action.ticket.subject,
        value=payload_value(action.action_type, action.payload),
        final_value=payload_value(action.action_type, action.final_payload)
        if action.final_payload
        else None,
        reason=action.reason,
        proposed_by=action.proposed_by,
        decided_by=action.decided_by,
        decided_at=action.decided_at,
        decision_note=action.decision_note,
        result=action.result,
        error=action.error,
        message_id=action.message_id,
        created_at=action.created_at,
    )
