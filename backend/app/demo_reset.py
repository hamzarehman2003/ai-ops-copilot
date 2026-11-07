"""Put the demo back to its starting state (between rehearsals or video takes). Dev only.

Keeps what is slow to rebuild: workspaces, users, and the indexed demo documents.
Removes what a demo run creates:
- conversations, messages, retrieval traces, tool calls;
- proposed actions and their audit events, CRM idempotency records;
- customers / tickets / ticket notes, re-seeded fresh (an approved action changes tickets);
- "deprecated" flags (the demo deprecates the legacy FAQ) and their audit events;
- documents uploaded during the demo (anything not in data/demo_docs or data/acme_docs).

The caller commits, then deletes `files_to_remove` (so a failed commit never loses files).
"""

from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app.models import (
    AuditEvent,
    Conversation,
    CrmOperation,
    Customer,
    ProposedAction,
    RetrievalTrace,
    SourceDocument,
    ToolCall,
    Workspace,
)
from app.seed import seed

DEMO_DOC_DIRS = {"tasklane-support": "demo_docs", "acme-demo": "acme_docs"}


@dataclass
class ResetResult:
    deleted: dict[str, int]
    reseeded: dict[str, int]
    removed_documents: list[str] = field(default_factory=list)
    files_to_remove: list[Path] = field(default_factory=list)


def demo_filenames(data_dir: Path) -> dict[str, set[str]]:
    """Workspace slug -> the demo filenames that belong to it."""
    return {
        slug: {p.name for p in (data_dir / folder).iterdir() if p.is_file()}
        for slug, folder in DEMO_DOC_DIRS.items()
    }


def reset_demo(session: Session, upload_dir: Path, keep: dict[str, set[str]]) -> ResetResult:
    deleted: dict[str, int] = {}

    def run(name: str, statement) -> None:
        deleted[name] = session.execute(statement).rowcount

    # Copilot activity and the action workflow.
    run("tool_calls", delete(ToolCall))
    run("retrieval_traces", delete(RetrievalTrace))
    run("conversations", delete(Conversation))  # messages cascade
    run("proposed_actions", delete(ProposedAction))
    run(
        "audit_events",
        delete(AuditEvent).where(
            or_(
                AuditEvent.entity_type == "proposed_action",
                AuditEvent.event_type.in_(["source.deprecated", "source.restored"]),
            )
        ),
    )
    run("crm_operations", delete(CrmOperation))

    # Documents uploaded during the demo (rows cascade to versions and chunks).
    slugs = dict(session.execute(select(Workspace.id, Workspace.slug)).all())
    removed, files = [], []
    for doc in session.scalars(select(SourceDocument)).all():
        if doc.filename in keep.get(slugs[doc.workspace_id], set()):
            continue
        ids = [str(doc.id), *(str(v.id) for v in doc.versions)]
        files += [upload_dir / v.storage_path for v in doc.versions]
        session.execute(delete(AuditEvent).where(AuditEvent.entity_id.in_(ids)))
        session.delete(doc)
        removed.append(f"{slugs[doc.workspace_id]}/{doc.filename}")
    run(
        "deprecated_flags",
        update(SourceDocument).where(SourceDocument.deprecated.is_(True)).values(deprecated=False),
    )

    # CRM back to the seed: customers cascade to tickets and notes; seed() re-inserts them.
    run("customers", delete(Customer))
    session.flush()
    reseeded = seed(session)
    return ResetResult(deleted, reseeded, removed, files)
