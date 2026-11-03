import uuid

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Chunk,
    DocumentVersion,
    IngestionStatus,
    SourceDocument,
    SourceType,
    Workspace,
)


def make_document(session: Session) -> SourceDocument:
    workspace = Workspace(name="Test Co", slug=f"test-{uuid.uuid4().hex[:8]}")
    document = SourceDocument(
        workspace=workspace,
        title="Billing and Refund Policy",
        filename="billing-and-refunds-policy.pdf",
        source_type=SourceType.PDF,
    )
    session.add(document)
    session.flush()
    return document


def make_version(
    session: Session, document: SourceDocument, number: int, content_hash: str, **kwargs
) -> DocumentVersion:
    version = DocumentVersion(
        document=document,
        version_number=number,
        content_hash=content_hash,
        storage_path=f"/uploads/{document.id}/v{number}",
        file_size_bytes=1024,
        **kwargs,
    )
    session.add(version)  # SQLAlchemy 2 does not cascade into the session via backrefs
    return version


def test_document_version_chunks_roundtrip(session: Session):
    document = make_document(session)
    version = make_version(session, document, 1, "a" * 64, is_current=True)
    version.chunks = [
        Chunk(
            workspace_id=document.workspace_id,
            chunk_index=i,
            content=f"chunk {i}",
            token_count=2,
            page_start=1,
            page_end=1,
            char_start=i * 10,
            char_end=i * 10 + 7,
            heading_path=["Billing and Refund Policy", "4. Refund eligibility"],
            chunk_metadata={"section": "4"},
        )
        for i in range(3)
    ]
    session.flush()
    session.expire_all()

    loaded = session.get(DocumentVersion, version.id)
    assert loaded.status == IngestionStatus.PENDING  # default
    assert [c.chunk_index for c in loaded.chunks] == [0, 1, 2]
    assert loaded.chunks[0].heading_path == ["Billing and Refund Policy", "4. Refund eligibility"]
    assert loaded.chunks[0].chunk_metadata == {"section": "4"}
    assert loaded.document.workspace.slug.startswith("test-")


def test_same_content_hash_twice_is_rejected(session: Session):
    document = make_document(session)
    make_version(session, document, 1, "b" * 64)
    session.flush()

    make_version(session, document, 2, "b" * 64)
    with pytest.raises(IntegrityError, match="uq_document_versions_document_id_content_hash"):
        session.flush()


def test_only_one_current_version_per_document(session: Session):
    document = make_document(session)
    make_version(session, document, 1, "c" * 64, is_current=True)
    session.flush()

    make_version(session, document, 2, "d" * 64, is_current=True)
    with pytest.raises(IntegrityError, match="uq_document_versions_one_current"):
        session.flush()


def test_deleting_document_cascades_in_database(session: Session):
    document = make_document(session)
    version = make_version(session, document, 1, "e" * 64)
    version.chunks = [
        Chunk(
            workspace_id=document.workspace_id,
            chunk_index=0,
            content="x",
            token_count=1,
            char_start=0,
            char_end=1,
        )
    ]
    session.flush()
    version_id = version.id

    def counts() -> tuple[int, int]:
        n_versions = session.scalar(
            select(func.count())
            .select_from(DocumentVersion)
            .where(DocumentVersion.id == version_id)
        )
        n_chunks = session.scalar(
            select(func.count()).select_from(Chunk).where(Chunk.document_version_id == version_id)
        )
        return n_versions, n_chunks

    assert counts() == (1, 1)  # rows really exist before the delete

    # Plain SQL delete: proves ON DELETE CASCADE works in Postgres, not just in the ORM.
    session.execute(delete(SourceDocument).where(SourceDocument.id == document.id))
    session.expire_all()

    assert counts() == (0, 0)


def test_invalid_status_rejected_by_check_constraint(session: Session):
    document = make_document(session)
    version = make_version(session, document, 1, "f" * 64)
    session.flush()

    with pytest.raises(IntegrityError, match="ck_document_versions_ingestion_status"):
        session.execute(
            text("UPDATE document_versions SET status = 'banana' WHERE id = :id"),
            {"id": version.id},
        )
