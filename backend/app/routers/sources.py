import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.deps import SessionDep, SettingsDep, WorkspaceDep
from app.ingestion.upload import UploadError, register_upload
from app.models import SourceDocument
from app.schemas import SourceDetail, SourceSummary, SourceUploadResponse, VersionOut

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
    workspace: WorkspaceDep,
    session: SessionDep,
    settings: SettingsDep,
    file: Annotated[UploadFile, File()],
    title: Annotated[str | None, Form(max_length=500)] = None,
) -> SourceUploadResponse:
    """Upload a PDF, Markdown, HTML, or text file as a new version of a source document."""
    data = _read_limited(file, settings.max_upload_bytes)
    try:
        result = register_upload(
            session, workspace, file.filename, data, settings.upload_dir, title=title
        )
    except UploadError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc

    if result.duplicate:
        response.status_code = status.HTTP_200_OK

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
