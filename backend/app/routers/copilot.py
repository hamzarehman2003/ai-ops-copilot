import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.deps import CurrentUser, SessionDep, SettingsDep, WorkspaceDep
from app.generation.copilot import ask, citation_list, proposal_summary, source_list
from app.generation.llm import get_llm
from app.models import Customer, Message, RetrievalTrace, ToolCall
from app.retrieval.search import chunk_to_dict, retrieve
from app.schemas import FeedbackIn, QueryIn

router = APIRouter(prefix="/api", tags=["copilot"])


@router.post("/copilot/query")
def query(body: QueryIn, user: CurrentUser, session: SessionDep, settings: SettingsDep) -> dict:
    """Ask the copilot. `customer_id` (optional) is the customer the agent is working on."""
    customer = None
    if body.customer_id is not None:
        customer = session.scalar(
            select(Customer).where(
                Customer.id == body.customer_id, Customer.workspace_id == user.workspace_id
            )
        )
        if customer is None:  # another tenant's customer looks exactly like a missing one
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")

    run = ask(
        session,
        settings,
        user,
        body.question,
        customer=customer,
        conversation_id=body.conversation_id,
        llm=get_llm(settings),
    )
    return {
        "conversation_id": run.conversation.id,
        "message_id": run.message.id,
        "answer": run.payload.answer,
        "abstained": run.payload.abstained,
        "missing_information": run.payload.missing_information,
        "citations": citation_list(run),
        "sources": source_list(run),
        "tool_calls": [_tool_call(c) for c in run.tool_ctx.calls],
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
    retrieval = session.scalar(
        select(RetrievalTrace).where(RetrievalTrace.message_id == message_id)
    )
    calls = session.scalars(
        select(ToolCall).where(ToolCall.message_id == message_id).order_by(ToolCall.created_at)
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
        "tool_calls": [_tool_call(c) for c in calls],
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


def _tool_call(call: ToolCall) -> dict:
    return {
        "id": call.id,
        "tool_name": call.tool_name,
        "arguments": call.arguments,
        "status": call.status,
        "error_code": call.error_code,
        "attempts": call.attempts,
        "latency_ms": call.latency_ms,
        "result": call.result,
    }
