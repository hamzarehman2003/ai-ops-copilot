"""scripts/reset_demo: a demo run's changes are undone; users and indexed demo docs stay."""

from pathlib import Path

from sqlalchemy import func, select

from app.demo_reset import demo_filenames, reset_demo
from app.generation.copilot import ask
from app.ingestion.upload import register_upload
from app.models import (
    AuditEvent,
    Conversation,
    Customer,
    ProposedAction,
    SourceDocument,
    Ticket,
    User,
    Workspace,
)
from app.tools.actions import approve_action, propose_action
from app.tools.crm import MockCrm

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def count(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


def test_reset_undoes_a_demo_run(indexed):
    session, settings = indexed.session, indexed.settings
    agent = session.scalar(select(User).where(User.email == "agent@tasklane.example"))
    brightpath = session.scalar(select(Customer).where(Customer.external_id == "CUST-1001"))
    docs_before = count(session, SourceDocument)
    ticket_before = session.scalar(select(Ticket).where(Ticket.external_id == "TCK-2041"))
    tags_before = list(ticket_before.tags)

    # A demo run: a question, an approved action that changes a ticket, a deprecated doc,
    # and a document uploaded on camera.
    ask(session, settings, agent, "Why is Brightpath suspended?", customer=brightpath)
    action = propose_action(
        session,
        workspace_id=agent.workspace_id,
        customer_id=brightpath.id,
        proposed_by=agent,
        ticket_external_id="TCK-2041",
        action_type="add_ticket_tag",
        value="demo-tag",
    )
    approve_action(session, action, agent, MockCrm(session, settings))
    session.execute(
        SourceDocument.__table__.update()
        .where(SourceDocument.filename == "legacy-pricing-faq-2024.md")
        .values(deprecated=True)
    )
    workspace = session.scalar(select(Workspace).where(Workspace.slug == "tasklane-support"))
    upload = register_upload(
        session, workspace, "live-upload.md", b"# Live\n\nUploaded on camera.", settings.upload_dir
    )
    session.flush()
    assert "demo-tag" in session.scalar(select(Ticket).where(Ticket.external_id == "TCK-2041")).tags

    result = reset_demo(session, settings.upload_dir, demo_filenames(DATA_DIR))
    session.expire_all()

    assert count(session, Conversation) == 0
    assert count(session, ProposedAction) == 0
    assert (
        session.scalar(select(func.count()).where(AuditEvent.entity_type == "proposed_action")) == 0
    )
    assert result.removed_documents == ["tasklane-support/live-upload.md"]
    assert result.files_to_remove == [settings.upload_dir / upload.version.storage_path]
    assert count(session, SourceDocument) == docs_before  # demo docs kept, still indexed
    assert not session.scalar(select(func.bool_or(SourceDocument.deprecated)))
    ticket = session.scalar(select(Ticket).where(Ticket.external_id == "TCK-2041"))
    assert ticket.tags == tags_before and ticket.notes == []
    assert result.reseeded["customers"] == count(session, Customer)
    assert count(session, User) == 5
