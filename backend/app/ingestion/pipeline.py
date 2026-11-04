"""Process one uploaded version: parse -> chunk -> embed -> save chunks -> make it current.

Runs after the upload response (FastAPI BackgroundTasks) or from `reindex`. The version only
becomes `is_current` after everything succeeded, in one transaction with the swap, so
retrieval never sees a half-indexed version and the previous version keeps serving until then.
"""

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from app.config import Settings
from app.ingestion.chunking import chunk_document
from app.ingestion.embeddings import Embedder, embedding_text, get_embedder
from app.ingestion.parsing import ParseError, parse
from app.models import AuditEvent, Chunk, DocumentVersion, IngestionStatus
from app.storage import read_file

logger = logging.getLogger(__name__)


def process_version(
    session: Session,
    version_id: uuid.UUID,
    settings: Settings,
    embedder: Embedder | None = None,
) -> DocumentVersion:
    version = session.get(DocumentVersion, version_id)
    if version is None:
        raise ValueError(f"Version {version_id} not found")

    version.status = IngestionStatus.PROCESSING
    version.error_message = None
    session.commit()

    try:
        _index_version(session, version, settings, embedder or get_embedder())
    except Exception as exc:  # any failure leaves the old current version serving
        session.rollback()
        version.status = IngestionStatus.FAILED
        version.error_message = (
            str(exc) if isinstance(exc, ParseError) else f"{type(exc).__name__}: {exc}"
        )[:2000]
        session.commit()
        logger.exception("Processing failed for version %s", version_id)
    return version


def _index_version(
    session: Session, version: DocumentVersion, settings: Settings, embedder: Embedder
) -> None:
    document = version.document
    doc = parse(document.source_type, read_file(settings.upload_dir, version.storage_path))
    drafts = chunk_document(doc)
    vectors = embedder.embed_documents([embedding_text(d.heading_path, d.content) for d in drafts])

    # Re-processing (reindex) replaces this version's chunks.
    session.execute(delete(Chunk).where(Chunk.document_version_id == version.id))
    session.add_all(
        Chunk(
            workspace_id=document.workspace_id,  # from the document, never from user input
            document_version_id=version.id,
            chunk_index=i,
            content=draft.content,
            token_count=draft.token_count,
            page_start=draft.page_start,
            page_end=draft.page_end,
            char_start=draft.char_start,
            char_end=draft.char_end,
            heading_path=draft.heading_path,
            heading_text=" > ".join(draft.heading_path),
            chunk_metadata={"contains_table": draft.contains_table},
            embedding=vector,
            embedding_model=embedder.model_name,
        )
        for i, (draft, vector) in enumerate(zip(drafts, vectors, strict=True))
    )

    # Swap: the old current version off first (partial unique index), then this one on.
    session.execute(
        update(DocumentVersion)
        .where(DocumentVersion.document_id == document.id, DocumentVersion.id != version.id)
        .values(is_current=False)
    )
    session.flush()
    version.is_current = True
    version.status = IngestionStatus.READY
    version.processed_at = datetime.now(UTC)
    session.add(
        AuditEvent(
            workspace_id=document.workspace_id,
            event_type="source.indexed",
            entity_type="document_version",
            entity_id=str(version.id),
            data={
                "document": document.filename,
                "version": version.version_number,
                "chunks": len(drafts),
                "embedding_model": embedder.model_name,
            },
        )
    )
    session.commit()


def process_in_background(
    session_factory: Callable[[], Session], version_id: uuid.UUID, settings: Settings
) -> None:
    """Entry point for BackgroundTasks: its own session, since the request's is closed."""
    with session_factory() as session:
        process_version(session, version_id, settings)
