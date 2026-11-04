"""API response models. Internal fields (e.g. storage_path) are deliberately not exposed."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import ActionStatus, IngestionStatus, SourceType, UserRole


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
    deprecated: bool
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


class ChunkOut(BaseModel):
    id: uuid.UUID
    chunk_index: int
    version_number: int
    heading_path: list[str]
    content: str
    token_count: int
    page_start: int | None
    page_end: int | None
    char_start: int
    char_end: int
    contains_table: bool
    embedding_model: str | None

    @classmethod
    def from_chunk(cls, chunk, version_number: int) -> "ChunkOut":
        return cls(
            id=chunk.id,
            chunk_index=chunk.chunk_index,
            version_number=version_number,
            heading_path=list(chunk.heading_path),
            content=chunk.content,
            token_count=chunk.token_count,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            char_start=chunk.char_start,
            char_end=chunk.char_end,
            contains_table=bool(chunk.chunk_metadata.get("contains_table")),
            embedding_model=chunk.embedding_model,
        )


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str
    role: UserRole
    workspace_id: uuid.UUID


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    external_id: str
    name: str
    plan: str
    account_status: str


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    external_id: str
    subject: str
    body: str
    status: str
    priority: str
    tags: list[str]
    created_at: datetime


class QueryIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    customer_id: uuid.UUID | None = None  # chosen by the human; checked against the workspace
    conversation_id: uuid.UUID | None = None


class FeedbackIn(BaseModel):
    feedback: Literal["helpful", "unhelpful"]


class ActionOut(BaseModel):
    id: uuid.UUID
    action_type: str
    status: ActionStatus
    customer: str
    ticket: str
    ticket_subject: str
    value: str
    final_value: str | None
    reason: str
    proposed_by: uuid.UUID
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    decision_note: str | None
    result: dict | None
    error: str | None
    message_id: uuid.UUID | None
    created_at: datetime


class DecisionIn(BaseModel):
    edited_value: str | None = Field(default=None, max_length=2000)
    note: str | None = Field(default=None, max_length=1000)


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    actor_name: str | None = None
    event_type: str
    entity_type: str
    entity_id: str
    data: dict
    created_at: datetime


class SourceUpdate(BaseModel):
    deprecated: bool
