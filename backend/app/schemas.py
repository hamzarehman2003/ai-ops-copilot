"""API response models. Internal fields (e.g. storage_path) are deliberately not exposed."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models import IngestionStatus, SourceType


class VersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version_number: int
    content_hash: str
    file_size_bytes: int
    status: IngestionStatus
    is_current: bool
    error_message: str | None
    created_at: datetime
    processed_at: datetime | None


class SourceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    filename: str
    source_type: SourceType
    created_at: datetime
    updated_at: datetime
    latest_version: VersionOut | None


class SourceDetail(SourceSummary):
    versions: list[VersionOut]


class SourceUploadResponse(BaseModel):
    document_id: uuid.UUID
    title: str
    filename: str
    source_type: SourceType
    duplicate: bool  # true: identical bytes already uploaded; nothing new was stored
    version: VersionOut
