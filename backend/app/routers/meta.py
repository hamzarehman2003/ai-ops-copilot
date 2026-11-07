"""Who am I, which models/prompt/index versions are live, and the latest eval report."""

import json

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.deps import CurrentUser, SessionDep, SettingsDep, WorkspaceDep
from app.generation.prompts import PROMPT_VERSION
from app.models import Chunk, DocumentVersion, User
from app.schemas import UserOut

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/me")
def me(user: CurrentUser) -> dict:
    return {
        "user": UserOut.model_validate(user),
        "workspace": {
            "id": user.workspace.id,
            "name": user.workspace.name,
            "slug": user.workspace.slug,
        },
    }


@router.get("/users")
def list_users(session: SessionDep) -> list[dict]:
    """Users the UI can switch between (stand-in until real auth replaces `get_current_user`)."""
    users = session.scalars(select(User).order_by(User.email))
    return [
        {
            "id": u.id,
            "email": u.email,
            "name": u.name,
            "role": u.role,
            "workspace": u.workspace.slug,
            "workspace_name": u.workspace.name,
        }
        for u in users
    ]


@router.get("/meta")
def meta(workspace: WorkspaceDep, session: SessionDep, settings: SettingsDep) -> dict:
    """Versions that define how answers are produced; evals record the same fields."""
    chunks = session.scalar(
        select(func.count())
        .select_from(Chunk)
        .join(DocumentVersion, DocumentVersion.id == Chunk.document_version_id)
        .where(Chunk.workspace_id == workspace.id, DocumentVersion.is_current.is_(True))
    )
    return {
        "llm": {
            "enabled": settings.llm_enabled,
            "provider": settings.llm_provider if settings.llm_enabled else None,
            "model": settings.llm_model if settings.llm_enabled else None,
            "effort": settings.llm_effort if settings.llm_enabled else None,
        },
        "prompt_version": PROMPT_VERSION,
        "embedding_model": settings.embedding_model,
        "reranker_model": settings.reranker_model,
        "retrieval": {
            "mode": settings.retrieval_mode,
            "k": settings.retrieval_k,
            "candidates": settings.retrieval_candidates,
            "rrf_k": settings.rrf_k,
            "min_rerank_score": settings.min_rerank_score,
        },
        "index": {"current_chunks": chunks},
    }


@router.get("/evaluations/latest")
def latest_evaluation(user: CurrentUser, settings: SettingsDep) -> dict:
    path = settings.eval_results_dir / "latest.json"
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No evaluation has been run yet")
    return json.loads(path.read_text(encoding="utf-8"))
