"""Mock CRM / helpdesk API.

Stands in for an external system (Zendesk, HubSpot, ...) that the copilot reads from and,
after human approval, writes to. It runs in-process over our own tables, but behaves like a
remote API on purpose:
- every call is scoped to a workspace (the CRM's own tenant check, defense in depth);
- calls can be slow, fail, or return malformed data (`crm_fault` / `crm_latency_s`), so the
  tool layer's timeouts, retries, and response validation can be tested;
- writes take an idempotency key: replaying the same key returns the first result instead of
  writing twice (what you need when a retry follows a timeout whose write actually landed).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import CrmOperation, Customer, Ticket, TicketNote


class CrmError(Exception):
    code = "CRM_ERROR"
    retryable = False


class CrmTimeout(CrmError):
    code = "TIMEOUT"
    retryable = True


class CrmUnavailable(CrmError):
    code = "UNAVAILABLE"
    retryable = True


class CrmNotFound(CrmError):
    code = "NOT_FOUND"


class MockCrm:
    def __init__(self, session: Session, settings: Settings, fault: str | None = None) -> None:
        self.session = session
        self.timeout_s = settings.crm_timeout_s
        self.max_retries = settings.crm_max_retries
        self.latency_s = settings.crm_latency_s
        self.fault = fault or settings.crm_fault

    # --- reads ---------------------------------------------------------------------------

    def get_account(self, workspace_id: uuid.UUID, customer_id: uuid.UUID) -> dict:
        self._simulate_network()
        customer = self._customer(workspace_id, customer_id)
        if self.fault == "malformed":
            return {"customer": customer.external_id, "status": 42}  # wrong shape on purpose
        return {
            "customer_id": customer.external_id,
            "name": customer.name,
            "plan": customer.plan,
            "account_status": customer.account_status,
            "seats_paid": customer.seats_paid,
            "seats_used": customer.seats_used,
            "sso_enabled": customer.sso_enabled,
            "renewal_date": customer.renewal_date.isoformat() if customer.renewal_date else None,
            "billing_note": customer.billing_note,
        }

    def list_tickets(self, workspace_id: uuid.UUID, customer_id: uuid.UUID, limit: int) -> list:
        self._simulate_network()
        self._customer(workspace_id, customer_id)
        tickets = self.session.scalars(
            select(Ticket)
            .where(Ticket.workspace_id == workspace_id, Ticket.customer_id == customer_id)
            .order_by(Ticket.created_at.desc())
            .limit(limit)
        )
        if self.fault == "malformed":
            return [{"oops": True}]
        return [
            {
                "ticket_id": t.external_id,
                "subject": t.subject,
                "status": t.status,
                "priority": t.priority,
                "tags": list(t.tags),
                "created_at": t.created_at.isoformat(),
                "body": t.body,
            }
            for t in tickets
        ]

    # --- writes (idempotent) ---------------------------------------------------------------

    def apply(
        self,
        workspace_id: uuid.UUID,
        ticket_id: uuid.UUID,
        action_type: str,
        payload: dict,
        author: str,
        idempotency_key: str,
    ) -> dict:
        previous = self.session.get(CrmOperation, idempotency_key)
        if previous is not None:  # replay: same answer, no second write
            return {**previous.result, "replayed": True}

        self._simulate_network()
        ticket = self.session.scalar(
            select(Ticket).where(Ticket.id == ticket_id, Ticket.workspace_id == workspace_id)
        )
        if ticket is None:
            raise CrmNotFound(f"Ticket {ticket_id} not found")

        if action_type == "add_ticket_note":
            note = TicketNote(ticket_id=ticket.id, body=payload["note"], author=author)
            self.session.add(note)
            self.session.flush()
            result = {"ticket_id": ticket.external_id, "note_id": str(note.id)}
        elif action_type == "add_ticket_tag":
            if payload["tag"] not in ticket.tags:
                ticket.tags = [*ticket.tags, payload["tag"]]
            result = {"ticket_id": ticket.external_id, "tags": list(ticket.tags)}
        elif action_type == "set_ticket_status":
            ticket.status = payload["status"]
            result = {"ticket_id": ticket.external_id, "status": ticket.status}
        else:
            raise CrmError(f"Unsupported operation {action_type}")

        result["applied_at"] = datetime.now(UTC).isoformat()
        self.session.add(
            CrmOperation(
                idempotency_key=idempotency_key,
                workspace_id=workspace_id,
                operation=action_type,
                result=result,
            )
        )
        self.session.flush()
        return result

    # --- helpers ---------------------------------------------------------------------------

    def _simulate_network(self) -> None:
        if self.fault == "timeout" or self.latency_s > self.timeout_s:
            raise CrmTimeout(f"CRM did not answer within {self.timeout_s}s")
        if self.fault == "error":
            raise CrmUnavailable("CRM returned 503")

    def _customer(self, workspace_id: uuid.UUID, customer_id: uuid.UUID) -> Customer:
        customer = self.session.scalar(
            select(Customer).where(
                Customer.id == customer_id, Customer.workspace_id == workspace_id
            )
        )
        if customer is None:
            raise CrmNotFound(f"Customer {customer_id} not found")
        return customer
