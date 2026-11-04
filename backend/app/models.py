"""Database models.

Knowledge (RAG):
    workspaces 1──* source_documents 1──* document_versions 1──* chunks (text + embedding)

Mock CRM / support system (what the read-only tools and approved actions touch):
    workspaces 1──* customers 1──* tickets 1──* ticket_notes

Copilot runs, and everything recorded for audit:
    conversations 1──* messages; retrieval_traces, tool_calls, proposed_actions, audit_events
"""

import enum
import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Deterministic constraint names, so migrations can reference/drop them reliably.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class SourceType(enum.StrEnum):
    PDF = "pdf"
    MARKDOWN = "markdown"
    HTML = "html"
    TEXT = "text"


class IngestionStatus(enum.StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class UserRole(enum.StrEnum):
    ADMIN = "admin"  # manage sources, approve actions, everything an agent can do
    AGENT = "agent"  # ask the copilot, approve/reject actions
    VIEWER = "viewer"  # ask the copilot, read-only (cannot approve)


class ActionStatus(enum.StrEnum):
    PENDING = "pending"
    APPROVED = "approved"  # a human said yes; the executor may run it (and only then)
    REJECTED = "rejected"
    EXECUTED = "executed"
    FAILED = "failed"


class ToolCallStatus(enum.StrEnum):
    OK = "ok"
    ERROR = "error"
    DENIED = "denied"  # authorization check failed (e.g. a customer outside the caller's scope)
    TIMEOUT = "timeout"


EMBEDDING_DIM = 384  # BAAI/bge-small-en-v1.5; changing models with another size = new column


def _str_enum(enum_cls: type[enum.StrEnum], name: str) -> Enum:
    """Store enum values as varchar + CHECK constraint (easier to evolve than native PG enums)."""
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=20,
        values_callable=lambda e: [member.value for member in e],
    )


class Workspace(Base):
    """A tenant: one company using the copilot. Every document and chunk belongs to one."""

    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    documents: Mapped[list["SourceDocument"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan", passive_deletes=True
    )


class SourceDocument(Base):
    """A logical document, e.g. "the billing policy". Its content lives in versions."""

    __tablename__ = "source_documents"
    __table_args__ = (UniqueConstraint("workspace_id", "filename"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(500))
    filename: Mapped[str] = mapped_column(String(500))
    source_type: Mapped[SourceType] = mapped_column(_str_enum(SourceType, "source_type"))
    # Outdated/superseded content stays stored (audit, history) but is excluded from retrieval.
    deprecated: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    workspace: Mapped[Workspace] = relationship(back_populates="documents")
    versions: Mapped[list["DocumentVersion"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="DocumentVersion.version_number",
    )

    @property
    def latest_version(self) -> "DocumentVersion | None":
        return self.versions[-1] if self.versions else None


class DocumentVersion(Base):
    """One uploaded content of a document. Re-uploading changed bytes creates a new version."""

    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_number"),
        # Same bytes uploaded twice for a document -> rejected, so we never re-embed for nothing.
        UniqueConstraint("document_id", "content_hash"),
        # At most one current version per document.
        Index(
            "uq_document_versions_one_current",
            "document_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_documents.id", ondelete="CASCADE")
    )
    version_number: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))  # SHA-256 hex of the file bytes
    storage_path: Mapped[str] = mapped_column(String(1000))
    file_size_bytes: Mapped[int] = mapped_column(Integer)
    status: Mapped[IngestionStatus] = mapped_column(
        _str_enum(IngestionStatus, "ingestion_status"),
        default=IngestionStatus.PENDING,
        server_default=IngestionStatus.PENDING.value,
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    document: Mapped[SourceDocument] = relationship(back_populates="versions")
    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document_version",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Chunk.chunk_index",
    )


class Chunk(Base):
    """A searchable piece of a document version. Becomes "the vector DB" once embedded."""

    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_version_id", "chunk_index"),
        # Approximate nearest-neighbour index for cosine distance (the `<=>` operator).
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        # Full-text (keyword) index for the lexical half of hybrid search.
        Index("ix_chunks_search_vector", "search_vector", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Denormalized on purpose: retrieval filters by tenant directly on this table,
    # inside the vector query, without joining up to source_documents.
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE")
    )
    chunk_index: Mapped[int] = mapped_column(Integer)  # position within the version
    content: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer)
    page_start: Mapped[int | None] = mapped_column(Integer)  # PDFs only
    page_end: Mapped[int | None] = mapped_column(Integer)
    char_start: Mapped[int] = mapped_column(Integer)  # offsets into the normalized text
    char_end: Mapped[int] = mapped_column(Integer)
    heading_path: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=text("'{}'")
    )  # e.g. ["Billing and Refund Policy", "4. Refund eligibility"]
    # "metadata" is reserved on declarative classes, so the attribute name differs.
    chunk_metadata: Mapped[dict] = mapped_column(
        "metadata", JSONB, server_default=text("'{}'::jsonb")
    )
    # Vector of the *embedded* text (heading path + content), not of `content` alone.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    embedding_model: Mapped[str | None] = mapped_column(String(100))  # vectors are model-specific
    # "A > B" form of heading_path. A plain column because generated columns may only use
    # immutable functions, and array_to_string() is not.
    heading_text: Mapped[str] = mapped_column(Text, server_default="")
    # Kept in sync by Postgres itself; includes the headings so keyword search sees topics.
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', heading_text || ' ' || content)", persisted=True),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document_version: Mapped[DocumentVersion] = relationship(back_populates="chunks")


# --- Users -----------------------------------------------------------------------------------


class User(Base):
    """A support/ops person. Role and workspace are checked by backend code on every request."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[UserRole] = mapped_column(_str_enum(UserRole, "user_role"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    workspace: Mapped[Workspace] = relationship()


# --- Mock CRM / support system ---------------------------------------------------------------


class Customer(Base):
    """A (fictional) customer account of the SaaS company, as the CRM sees it."""

    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("workspace_id", "external_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    external_id: Mapped[str] = mapped_column(String(50))  # e.g. "CUST-1001"
    name: Mapped[str] = mapped_column(String(200))
    plan: Mapped[str] = mapped_column(String(50))  # free / pro / enterprise
    account_status: Mapped[str] = mapped_column(String(30))  # active, past_due, suspended...
    seats_paid: Mapped[int] = mapped_column(Integer)
    seats_used: Mapped[int] = mapped_column(Integer)
    sso_enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    renewal_date: Mapped[date | None] = mapped_column(Date)
    billing_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (UniqueConstraint("workspace_id", "external_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    external_id: Mapped[str] = mapped_column(String(50))  # e.g. "TCK-2041"
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))  # open / pending / solved
    priority: Mapped[str] = mapped_column(String(20), server_default="normal")
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    customer: Mapped[Customer] = relationship()
    notes: Mapped[list["TicketNote"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True, order_by="TicketNote.created_at"
    )


class TicketNote(Base):
    __tablename__ = "ticket_notes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), index=True
    )
    body: Mapped[str] = mapped_column(Text)
    author: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CrmOperation(Base):
    """The mock CRM's idempotency log: a retried write with the same key is applied once."""

    __tablename__ = "crm_operations"

    idempotency_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    operation: Mapped[str] = mapped_column(String(50))
    result: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# --- Copilot runs and audit trail ------------------------------------------------------------


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    # Insertion order. Timestamps can't order messages: now() is fixed per transaction.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    role: Mapped[str] = mapped_column(String(20))  # user / assistant
    content: Mapped[str] = mapped_column(Text)
    # Assistant messages: citations, abstained flag, mode, model/prompt versions, latency...
    data: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    feedback: Mapped[str | None] = mapped_column(String(20))  # helpful / unhelpful
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RetrievalTrace(Base):
    """What retrieval saw and returned for one query: enough to debug a bad answer later."""

    __tablename__ = "retrieval_traces"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    query: Mapped[str] = mapped_column(Text)
    params: Mapped[dict] = mapped_column(JSONB)  # k, candidates, weights, threshold, models
    results: Mapped[list] = mapped_column(JSONB)  # [{chunk_id, dense, lexical, rrf, rerank}]
    latency_ms: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    tool_name: Mapped[str] = mapped_column(String(100))
    arguments: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[ToolCallStatus] = mapped_column(_str_enum(ToolCallStatus, "tool_call_status"))
    result: Mapped[dict | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(100))
    attempts: Mapped[int] = mapped_column(Integer, server_default="1")
    latency_ms: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProposedAction(Base):
    """A write the copilot suggested. Nothing runs until a human approves it (rule 4)."""

    __tablename__ = "proposed_actions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL")
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"))
    ticket_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"))
    action_type: Mapped[str] = mapped_column(String(50))  # add_ticket_note, add_ticket_tag...
    payload: Mapped[dict] = mapped_column(JSONB)  # as proposed
    final_payload: Mapped[dict | None] = mapped_column(JSONB)  # as approved (maybe edited)
    reason: Mapped[str] = mapped_column(Text, server_default="")
    status: Mapped[ActionStatus] = mapped_column(
        _str_enum(ActionStatus, "action_status"),
        default=ActionStatus.PENDING,
        server_default=ActionStatus.PENDING.value,
    )
    proposed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True)
    result: Mapped[dict | None] = mapped_column(JSONB)  # what the CRM confirmed
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    ticket: Mapped[Ticket] = relationship()
    customer: Mapped[Customer] = relationship()


class AuditEvent(Base):
    """Append-only log of who did what (proposals, approvals, executions, uploads)."""

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    event_type: Mapped[str] = mapped_column(String(100))  # e.g. action.approved
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str] = mapped_column(String(100))
    data: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
