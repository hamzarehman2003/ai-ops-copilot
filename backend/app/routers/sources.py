import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.deps import AdminUser, SessionDep, SessionFactoryDep, SettingsDep, WorkspaceDep
from app.ingestion.pipeline import claim_version, process_in_background
from app.ingestion.upload import UploadError, register_upload
from app.models import AuditEvent, Chunk, DocumentVersion, IngestionStatus, SourceDocument
from app.schemas import (
    ChunkOut,
    SourceDetail,
    SourceSummary,
    SourceUpdate,
    SourceUploadResponse,
    VersionOut,
)

router = APIRouter(prefix="/api/sources", tags=["sources"])

READ_CHUNK_BYTES = 1024 * 1024


def _read_limited(file: UploadFile, limit: int) -> bytes:
    """Read the upload in chunks and stop as soon as it exceeds `limit`.

    Note: the multipart body is already spooled to a temp file by this point; a hard cap on
    request size belongs in the reverse proxy (e.g. nginx client_max_body_size) in production.
    """
    buffer = bytearray()
    while chunk := file.file.read(READ_CHUNK_BYTES):
        buffer += chunk
        if len(buffer) > limit:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"File exceeds {limit} bytes")
    return bytes(buffer)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={200: {"description": "Identical file already uploaded (duplicate: true)"}},
)
def upload_source(
    response: Response,
    admin: AdminUser,
    workspace: WorkspaceDep,
    session: SessionDep,
    session_factory: SessionFactoryDep,
    settings: SettingsDep,
    background: BackgroundTasks,
    file: Annotated[UploadFile, File()],
    title: Annotated[str | None, Form(max_length=500)] = None,
) -> SourceUploadResponse:
    """Upload a PDF, Markdown, HTML, or text file as a new version of a source document.

    A new version is processed (parse, chunk, embed, index) in the background after the
    response; poll GET /api/sources/{id} until its status is `ready` (or `failed`).
    """
    data = _read_limited(file, settings.max_upload_bytes)
    try:
        result = register_upload(
            session, workspace, file.filename, data, settings.upload_dir, title=title
        )
    except UploadError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc

    if result.duplicate:
        response.status_code = status.HTTP_200_OK
    else:
        session.add(
            AuditEvent(
                workspace_id=workspace.id,
                actor_user_id=admin.id,
                event_type="source.uploaded",
                entity_type="document_version",
                entity_id=str(result.version.id),
                data={"filename": result.version.document.filename},
            )
        )
        session.commit()
        background.add_task(process_in_background, session_factory, result.version.id, settings)

    document = result.version.document
    return SourceUploadResponse(
        document_id=document.id,
        title=document.title,
        filename=document.filename,
        source_type=document.source_type,
        duplicate=result.duplicate,
        version=VersionOut.model_validate(result.version),
    )


@router.get("")
def list_sources(workspace: WorkspaceDep, session: SessionDep) -> list[SourceSummary]:
    documents = session.scalars(
        select(SourceDocument)
        .where(SourceDocument.workspace_id == workspace.id)
        .options(selectinload(SourceDocument.versions))
        .order_by(SourceDocument.filename)
    )
    return [SourceSummary.model_validate(doc) for doc in documents]


@router.get("/{document_id}")
def get_source(
    document_id: uuid.UUID, workspace: WorkspaceDep, session: SessionDep
) -> SourceDetail:
    document = session.scalar(
        select(SourceDocument)
        .where(
            SourceDocument.id == document_id,
            # Tenant scope is part of the query: another workspace's document is "not found",
            # so we never reveal that it exists (404, not 403).
            SourceDocument.workspace_id == workspace.id,
        )
        .options(selectinload(SourceDocument.versions))
    )
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Source not found")
    return SourceDetail.model_validate(document)


def _document_or_404(session, workspace, document_id: uuid.UUID) -> SourceDocument:
    document = session.scalar(
        select(SourceDocument)
        .where(SourceDocument.id == document_id, SourceDocument.workspace_id == workspace.id)
        .options(selectinload(SourceDocument.versions))
    )
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Source not found")
    return document


@router.post("/{document_id}/reindex", status_code=status.HTTP_202_ACCEPTED)
def reindex_source(
    document_id: uuid.UUID,
    admin: AdminUser,
    workspace: WorkspaceDep,
    session: SessionDep,
    session_factory: SessionFactoryDep,
    settings: SettingsDep,
    background: BackgroundTasks,
) -> VersionOut:
    """Re-process the latest version (e.g. after changing the chunker or embedding model)."""
    document = _document_or_404(session, workspace, document_id)
    version = document.latest_version
    # Atomic claim: two quick clicks can't both start a run; a run that died mid-ingest
    # (stuck in "processing" past ingestion_stale_after_s) can be restarted.
    if not claim_version(
        session, version.id, settings, IngestionStatus.PENDING, claimed_by_reindex=True
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "Version is already being processed")
    session.commit()
    session.refresh(version)
    background.add_task(process_in_background, session_factory, version.id, settings)
    return VersionOut.model_validate(version)


@router.get("/{document_id}/chunks")
def list_chunks(
    document_id: uuid.UUID, workspace: WorkspaceDep, session: SessionDep
) -> list[ChunkOut]:
    """Chunks of the current version (or the latest one if none is current yet)."""
    document = _document_or_404(session, workspace, document_id)
    version = next((v for v in document.versions if v.is_current), document.latest_version)
    chunks = session.scalars(
        select(Chunk)
        .join(DocumentVersion, DocumentVersion.id == Chunk.document_version_id)
        .where(Chunk.document_version_id == version.id, Chunk.workspace_id == workspace.id)
        .order_by(Chunk.chunk_index)
    )
    return [ChunkOut.from_chunk(c, version.version_number) for c in chunks]


@router.patch("/{document_id}")
def update_source(
    document_id: uuid.UUID,
    body: SourceUpdate,
    admin: AdminUser,
    workspace: WorkspaceDep,
    session: SessionDep,
) -> SourceDetail:
    """Mark a document deprecated (excluded from retrieval, kept for history) or restore it."""
    document = _document_or_404(session, workspace, document_id)
    document.deprecated = body.deprecated
    session.add(
        AuditEvent(
            workspace_id=workspace.id,
            actor_user_id=admin.id,
            event_type="source.deprecated" if body.deprecated else "source.restored",
            entity_type="source_document",
            entity_id=str(document.id),
            data={"filename": document.filename},
        )
    )
    session.commit()
    return SourceDetail.model_validate(document)
