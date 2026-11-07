import hashlib
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_session
from app.deps import get_session_factory
from app.ingestion.pipeline import claim_version, process_version
from app.main import app
from app.models import DocumentVersion, IngestionStatus, User, UserRole, Workspace

MAX_BYTES = 1024
MARKDOWN = b"# Refunds\n\nAnnual plans: 14 days.\n"


@pytest.fixture
def upload_dir(tmp_path: Path) -> Path:
    return tmp_path / "uploads"


@pytest.fixture
def client(session: Session, session_factory, upload_dir: Path) -> Iterator[TestClient]:
    settings = Settings(upload_dir=upload_dir, max_upload_bytes=MAX_BYTES)
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_settings] = lambda: settings
    # Background ingestion runs in the same rolled-back test transaction.
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def workspaces(session: Session) -> None:
    a, b = Workspace(name="A", slug="ws-a"), Workspace(name="B", slug="ws-b")
    session.add_all([a, b])
    session.flush()
    session.add_all(
        [
            User(workspace_id=a.id, email="admin@ws-a.test", name="A", role=UserRole.ADMIN),
            User(workspace_id=a.id, email="viewer@ws-a.test", name="V", role=UserRole.VIEWER),
            User(workspace_id=b.id, email="admin@ws-b.test", name="B", role=UserRole.ADMIN),
        ]
    )
    session.flush()


def as_admin(workspace: str) -> dict:
    return {"X-User": f"admin@{workspace}.test"}


def upload(client: TestClient, filename: str, data: bytes, workspace: str = "ws-a", **form):
    return client.post(
        "/api/sources",
        headers=as_admin(workspace),
        files={"file": (filename, data)},
        data=form,
    )


def version_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(DocumentVersion))


def test_upload_creates_pending_version_and_stores_file(
    client: TestClient, session: Session, upload_dir: Path
):
    response = upload(client, "refund-policy.md", MARKDOWN)

    assert response.status_code == 201
    body = response.json()
    assert body["duplicate"] is False
    assert body["filename"] == "refund-policy.md"
    assert body["title"] == "Refund policy"
    assert body["source_type"] == "markdown"
    assert body["version"]["version_number"] == 1
    assert body["version"]["status"] == "pending"
    assert body["version"]["is_current"] is False
    assert body["version"]["content_hash"] == hashlib.sha256(MARKDOWN).hexdigest()
    assert "storage_path" not in body["version"]

    version = session.get(DocumentVersion, body["version"]["id"])
    assert (upload_dir / version.storage_path).read_bytes() == MARKDOWN


def test_same_bytes_again_is_duplicate(client: TestClient, session: Session):
    first = upload(client, "refund-policy.md", MARKDOWN)
    second = upload(client, "refund-policy.md", MARKDOWN)

    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert second.json()["version"]["id"] == first.json()["version"]["id"]
    assert version_count(session) == 1


def test_changed_bytes_create_new_version(client: TestClient, session: Session):
    first = upload(client, "refund-policy.md", MARKDOWN)
    second = upload(client, "refund-policy.md", MARKDOWN + b"\nUpdated.\n")

    assert second.status_code == 201
    assert second.json()["document_id"] == first.json()["document_id"]
    assert second.json()["version"]["version_number"] == 2
    assert version_count(session) == 2


@pytest.mark.parametrize(
    ("filename", "data", "expected_status"),
    [
        ("notes.docx", b"PK\x03\x04", 415),  # unsupported type
        ("fake.pdf", b"<html>not a pdf</html>", 415),  # extension lies
        ("latin1.txt", "café".encode("latin-1"), 415),  # not UTF-8
        ("empty.md", b"", 400),
        ("big.txt", b"x" * (MAX_BYTES + 1), 413),
    ],
)
def test_invalid_uploads_are_rejected(
    client: TestClient, session: Session, filename: str, data: bytes, expected_status: int
):
    response = upload(client, filename, data)

    assert response.status_code == expected_status, response.text
    assert version_count(session) == 0


def test_real_pdf_is_accepted(client: TestClient):
    response = upload(client, "policy.pdf", b"%PDF-1.7\n...")

    assert response.status_code == 201
    assert response.json()["source_type"] == "pdf"


def test_unknown_user_is_401(client: TestClient):
    response = upload(client, "refund-policy.md", MARKDOWN, workspace="nope")

    assert response.status_code == 401


def test_only_admins_can_upload(client: TestClient):
    response = client.post(
        "/api/sources",
        headers={"X-User": "viewer@ws-a.test"},
        files={"file": ("refund-policy.md", MARKDOWN)},
    )
    assert response.status_code == 403


def test_upload_is_indexed_in_background_and_chunks_are_listed(
    client: TestClient, session: Session
):
    created = upload(client, "refund-policy.md", MARKDOWN)
    document_id = created.json()["document_id"]

    # TestClient runs background tasks before returning, so processing is done here.
    detail = client.get(f"/api/sources/{document_id}", headers=as_admin("ws-a")).json()
    assert detail["latest_version"]["status"] == IngestionStatus.READY
    assert detail["latest_version"]["is_current"] is True

    chunks = client.get(f"/api/sources/{document_id}/chunks", headers=as_admin("ws-a")).json()
    assert [c["content"] for c in chunks] == ["Refunds\n\nAnnual plans: 14 days."]
    assert chunks[0]["embedding_model"] == "BAAI/bge-small-en-v1.5"
    # Another tenant can't see the chunks either.
    other = client.get(f"/api/sources/{document_id}/chunks", headers=as_admin("ws-b"))
    assert other.status_code == 404


def test_path_traversal_filename_is_neutralized(
    client: TestClient, session: Session, upload_dir: Path
):
    response = upload(client, "../../evil.md", MARKDOWN)

    assert response.status_code == 201
    assert response.json()["filename"] == "evil.md"
    version = session.get(DocumentVersion, response.json()["version"]["id"])
    stored = (upload_dir / version.storage_path).resolve()
    assert stored.is_relative_to(upload_dir.resolve())
    assert "evil" not in version.storage_path


def test_custom_title_is_used(client: TestClient):
    response = upload(client, "refund-policy.md", MARKDOWN, title="Refund Policy 2026")

    assert response.json()["title"] == "Refund Policy 2026"


def test_list_and_detail_are_scoped_to_workspace(client: TestClient):
    created = upload(client, "refund-policy.md", MARKDOWN, workspace="ws-a")
    document_id = created.json()["document_id"]

    own_list = client.get("/api/sources", headers=as_admin("ws-a"))
    assert [d["id"] for d in own_list.json()] == [document_id]
    assert own_list.json()[0]["latest_version"]["version_number"] == 1

    own_detail = client.get(f"/api/sources/{document_id}", headers=as_admin("ws-a"))
    assert own_detail.status_code == 200
    assert len(own_detail.json()["versions"]) == 1

    # Another tenant sees nothing, and gets 404 (not 403) for the document's ID.
    other_list = client.get("/api/sources", headers=as_admin("ws-b"))
    assert other_list.json() == []
    other_detail = client.get(f"/api/sources/{document_id}", headers=as_admin("ws-b"))
    assert other_detail.status_code == 404


# --- Reindex claims (no double processing, no version stuck in "processing") -----------------


def latest_version(session: Session, document_id: str) -> DocumentVersion:
    return session.scalar(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == uuid.UUID(document_id))
        .order_by(DocumentVersion.version_number.desc())
    )


def test_reindex_is_refused_while_a_live_run_holds_the_version(
    client: TestClient, session: Session
):
    document_id = upload(client, "refund-policy.md", MARKDOWN).json()["document_id"]
    version = latest_version(session, document_id)
    version.status = IngestionStatus.PROCESSING
    version.processing_started_at = datetime.now(UTC)
    session.flush()

    response = client.post(f"/api/sources/{document_id}/reindex", headers=as_admin("ws-a"))
    assert response.status_code == 409


def test_a_run_that_died_mid_ingest_can_be_reindexed(client: TestClient, session: Session):
    document_id = upload(client, "refund-policy.md", MARKDOWN).json()["document_id"]
    version = latest_version(session, document_id)
    version.status = IngestionStatus.PROCESSING
    version.processing_started_at = datetime.now(UTC) - timedelta(hours=1)  # worker crashed
    session.flush()

    response = client.post(f"/api/sources/{document_id}/reindex", headers=as_admin("ws-a"))
    assert response.status_code == 202
    session.refresh(version)
    assert version.status == IngestionStatus.READY  # the background run finished it


def test_only_one_of_two_reindex_clicks_wins(client: TestClient, session: Session):
    document_id = upload(client, "refund-policy.md", MARKDOWN).json()["document_id"]
    version = latest_version(session, document_id)
    settings = Settings()
    first = claim_version(
        session, version.id, settings, IngestionStatus.PENDING, claimed_by_reindex=True
    )
    second = claim_version(
        session, version.id, settings, IngestionStatus.PENDING, claimed_by_reindex=True
    )
    assert (first, second) == (True, False)


def test_the_pipeline_skips_a_version_another_worker_is_processing(
    client: TestClient, session: Session, upload_dir: Path
):
    document_id = upload(client, "refund-policy.md", MARKDOWN).json()["document_id"]
    version = latest_version(session, document_id)
    version.status = IngestionStatus.PROCESSING
    version.processing_started_at = datetime.now(UTC)
    session.flush()

    process_version(session, version.id, Settings(upload_dir=upload_dir))
    assert version.status == IngestionStatus.PROCESSING  # untouched: not ours to process


def test_an_oversized_upload_is_refused_before_the_body_is_read(client: TestClient):
    big = b"x" * (MAX_BYTES + 128 * 1024)  # past the limit plus the multipart allowance
    response = upload(client, "huge.txt", big)
    assert response.status_code == 413
    assert "exceeds" in response.json()["detail"]
