"""Upload registration: validate a file, fingerprint it, and record a new document version.

No FastAPI here, so this logic is easy to test and reuse (API, scripts, future sync jobs).
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import storage
from app.models import DocumentVersion, SourceDocument, SourceType, Workspace

EXTENSION_TYPES = {
    ".pdf": SourceType.PDF,
    ".md": SourceType.MARKDOWN,
    ".markdown": SourceType.MARKDOWN,
    ".html": SourceType.HTML,
    ".htm": SourceType.HTML,
    ".txt": SourceType.TEXT,
}


class UploadError(Exception):
    """A rejected upload, carrying the HTTP status the API should return."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass
class UploadResult:
    version: DocumentVersion
    duplicate: bool


def sanitize_filename(raw: str | None) -> str:
    """Keep only the base name: '../../x.md' -> 'x.md'. Used for display/dedupe, never as a path."""
    name = PurePosixPath((raw or "").replace("\\", "/")).name.strip()
    if not name or name in {".", ".."}:
        raise UploadError(400, "File must have a name")
    return name[:255]


def detect_source_type(filename: str) -> SourceType:
    source_type = EXTENSION_TYPES.get(Path(filename).suffix.lower())
    if source_type is None:
        allowed = ", ".join(sorted(EXTENSION_TYPES))
        raise UploadError(415, f"Unsupported file type. Allowed: {allowed}")
    return source_type


def validate_content(source_type: SourceType, data: bytes) -> None:
    """Check the bytes match the claimed type; the extension alone proves nothing."""
    if not data:
        raise UploadError(400, "File is empty")
    if source_type is SourceType.PDF:
        if not data.startswith(b"%PDF-"):
            raise UploadError(415, "File has a .pdf extension but is not a PDF")
        return
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UploadError(415, "Text files must be UTF-8 encoded") from exc


def default_title(filename: str) -> str:
    stem = Path(filename).stem.replace("-", " ").replace("_", " ").strip()
    return stem[:1].upper() + stem[1:] if stem else filename


def register_upload(
    session: Session,
    workspace: Workspace,
    raw_filename: str | None,
    data: bytes,
    storage_root: Path,
    title: str | None = None,
) -> UploadResult:
    """Validate and store an upload as a new `pending` version, or return the duplicate.

    The new version is NOT current: it becomes current only after successful processing,
    so retrieval never reads a half-processed version.
    """
    filename = sanitize_filename(raw_filename)
    source_type = detect_source_type(filename)
    validate_content(source_type, data)
    content_hash = hashlib.sha256(data).hexdigest()

    stored_path: str | None = None
    try:
        document = session.scalar(
            select(SourceDocument).where(
                SourceDocument.workspace_id == workspace.id,
                SourceDocument.filename == filename,
            )
        )
        if document is None:
            document = SourceDocument(
                workspace_id=workspace.id,
                title=title or default_title(filename),
                filename=filename,
                source_type=source_type,
            )
            session.add(document)
            session.flush()
        else:
            existing = session.scalar(
                select(DocumentVersion).where(
                    DocumentVersion.document_id == document.id,
                    DocumentVersion.content_hash == content_hash,
                )
            )
            if existing is not None:
                return UploadResult(version=existing, duplicate=True)
            if title:
                document.title = title

        latest = session.scalar(
            select(func.max(DocumentVersion.version_number)).where(
                DocumentVersion.document_id == document.id
            )
        )
        version_number = (latest or 0) + 1
        suffix = Path(filename).suffix.lower()
        stored_path = f"{workspace.id}/{document.id}/v{version_number}-{content_hash[:12]}{suffix}"

        version = DocumentVersion(
            document_id=document.id,
            version_number=version_number,
            content_hash=content_hash,
            storage_path=stored_path,
            file_size_bytes=len(data),
        )
        session.add(version)
        session.flush()

        storage.save_file(storage_root, stored_path, data)
        session.commit()
    except IntegrityError as exc:
        # A concurrent upload of the same document won the race for a unique constraint.
        session.rollback()
        if stored_path:
            storage.delete_file(storage_root, stored_path)
        raise UploadError(409, "Concurrent upload of this document; please retry") from exc
    except Exception:
        session.rollback()
        if stored_path:
            storage.delete_file(storage_root, stored_path)
        raise

    session.refresh(version)
    return UploadResult(version=version, duplicate=False)
