import json
import logging
import queue
import threading
import uuid
from collections.abc import Iterator
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import CurrentUser, SessionDep, SessionFactoryDep, SettingsDep, WorkspaceDep
from app.generation.copilot import (
    CopilotRun,
    ask,
    citation_list,
    proposal_summary,
    source_list,
    tool_source_ids,
)
from app.generation.llm import open_llm
from app.models import Customer, Message, RetrievalTrace, ToolCall, User
from app.retrieval.search import chunk_to_dict, retrieve
from app.schemas import FeedbackIn, QueryIn

router = APIRouter(prefix="/api", tags=["copilot"])
log = logging.getLogger(__name__)


@router.post("/copilot/query")
def query(body: QueryIn, user: CurrentUser, session: SessionDep, settings: SettingsDep) -> dict:
    """Ask the copilot. `customer_id` (optional) is the customer the agent is working on."""
    customer = _customer(session, user, body.customer_id)
    with open_llm(settings) as llm:
        run = ask(
            session,
            settings,
            user,
            body.question,
            customer=customer,
            conversation_id=body.conversation_id,
            llm=llm,
        )
    return _response(run)


class _ClientGone(Exception):
    """The browser closed the stream: stop before paying for more model calls."""


@router.post("/copilot/query/stream")
def query_stream(
    body: QueryIn,
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
    session_factory: SessionFactoryDep,
) -> StreamingResponse:
    """Same as /copilot/query, as Server-Sent Events: `progress` events while the copilot works
    (retrieval, each tool call, each model round, checks), then one `result` event with the
    /copilot/query body, or an `error` event. Authorization happens before the stream starts,
    so a bad customer is still a plain 404.

    The work runs in a thread with its own session (a Session must never be shared across
    threads); the request's session ends its read transaction before streaming starts."""
    customer = _customer(session, user, body.customer_id)
    user_id, customer_id = user.id, customer.id if customer else None
    session.rollback()  # end the read-only transaction: no pooled connection held while streaming
    events: queue.Queue = queue.Queue()
    client_gone = threading.Event()

    def progress(event: dict) -> None:
        if client_gone.is_set():
            raise _ClientGone
        events.put(("progress", event))

    def work() -> None:
        with session_factory() as worker_session, open_llm(settings) as llm:
            try:
                run = ask(
                    worker_session,
                    settings,
                    worker_session.get_one(User, user_id),
                    body.question,
                    customer=worker_session.get(Customer, customer_id) if customer_id else None,
                    conversation_id=body.conversation_id,
                    llm=llm,
                    on_progress=progress,
                )
                events.put(("result", _response(run)))
            except _ClientGone:
                log.info("copilot stream: client disconnected, stopped early")
                worker_session.rollback()
            except Exception:
                log.exception("copilot stream failed")
                worker_session.rollback()
                events.put(("error", {"detail": "The copilot failed while answering."}))
            finally:
                events.put(None)

    def stream() -> Iterator[str]:
        threading.Thread(target=work, daemon=True).start()
        try:
            while (item := events.get()) is not None:
                kind, data = item
                yield f"event: {kind}\ndata: {json.dumps(jsonable_encoder(data))}\n\n"
        finally:  # normal end, or the client went away (generator closed)
            client_gone.set()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        # no-transform: proxies (incl. the Next.js /api rewrite) must not gzip, which buffers
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


def _customer(session: Session, user: User, customer_id: uuid.UUID | None) -> Customer | None:
    if customer_id is None:
        return None
    customer = session.scalar(
        select(Customer).where(
            Customer.id == customer_id, Customer.workspace_id == user.workspace_id
        )
    )
    if customer is None:  # another tenant's customer looks exactly like a missing one
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    return customer


def _response(run: CopilotRun) -> dict:
    return {
        "conversation_id": run.conversation.id,
        "message_id": run.message.id,
        "answer": run.payload.answer,
        "abstained": run.payload.abstained,
        "missing_information": run.payload.missing_information,
        "citations": citation_list(run),
        "sources": source_list(run),
        "tool_calls": _tool_calls(run.tool_ctx.calls),
        "proposed_action": proposal_summary(run),
        "mode": run.mode,
        "model": run.model,
        "warnings": run.warnings,
        "retrieval": {
            "mode": run.retrieval.mode,
            "trace_id": run.retrieval.trace_id,
            "latency_ms": run.retrieval.latency_ms,
        },
        "latency_ms": run.latency_ms,
    }


@router.post("/copilot/messages/{message_id}/feedback", status_code=204)
def feedback(
    message_id: uuid.UUID, body: FeedbackIn, workspace: WorkspaceDep, session: SessionDep
) -> None:
    message = session.scalar(
        select(Message).where(
            Message.id == message_id,
            Message.workspace_id == workspace.id,
            Message.role == "assistant",
        )
    )
    if message is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    message.feedback = body.feedback
    session.commit()


@router.get("/copilot/messages/{message_id}/trace")
def trace(message_id: uuid.UUID, workspace: WorkspaceDep, session: SessionDep) -> dict:
    """Everything recorded for one answer: retrieval candidates/scores and tool calls."""
    message = session.scalar(
        select(Message).where(Message.id == message_id, Message.workspace_id == workspace.id)
    )
    if message is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    # Tenant condition on every query (rule 2), even though the message was already scoped.
    retrieval = session.scalar(
        select(RetrievalTrace).where(
            RetrievalTrace.message_id == message_id, RetrievalTrace.workspace_id == workspace.id
        )
    )
    calls = list(
        session.scalars(
            select(ToolCall)
            .where(ToolCall.message_id == message_id, ToolCall.workspace_id == workspace.id)
            .order_by(ToolCall.created_at)
        )
    )
    return {
        "message": {"id": message.id, "content": message.content, "data": message.data},
        "retrieval": None
        if retrieval is None
        else {
            "query": retrieval.query,
            "params": retrieval.params,
            "results": retrieval.results,
            "latency_ms": retrieval.latency_ms,
        },
        "tool_calls": _tool_calls(calls),
    }


@router.get("/search")
def search(
    workspace: WorkspaceDep,
    session: SessionDep,
    settings: SettingsDep,
    q: Annotated[str, Query(min_length=1, max_length=500)],
    mode: Literal["dense", "lexical", "hybrid", "hybrid_rerank"] | None = None,
    k: Annotated[int, Query(ge=1, le=20)] = 5,
) -> dict:
    """Retrieval only (no LLM): see what the copilot would read for a query."""
    result = retrieve(
        session,
        workspace.id,
        q,
        settings,
        mode=mode,
        k=k,
        apply_threshold=False,
        save_trace=False,
    )
    return {
        "query": q,
        "mode": result.mode,
        "latency_ms": result.latency_ms,
        "params": result.params,
        "results": [chunk_to_dict(c) for c in result.chunks],
    }


def _tool_calls(calls: list[ToolCall]) -> list[dict]:
    sids = tool_source_ids(calls)
    return [_tool_call(c, sids.get(c.id)) for c in calls]


def _tool_call(call: ToolCall, source_id: str | None) -> dict:
    return {
        "id": call.id,
        "source_id": source_id,  # [T#] when the call succeeded (citable)
        "tool_name": call.tool_name,
        "arguments": call.arguments,
        "status": call.status,
        "error_code": call.error_code,
        "attempts": call.attempts,
        "latency_ms": call.latency_ms,
        "result": call.result,
    }
