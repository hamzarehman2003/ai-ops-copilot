from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import get_session

router = APIRouter(tags=["health"])


@router.get("/health")
def health(response: Response, session: Annotated[Session, Depends(get_session)]) -> dict:
    """Reports API, database, and pgvector status. Returns 503 if the DB is unusable."""
    try:
        pgvector_version = session.execute(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        ).scalar_one_or_none()
    except SQLAlchemyError:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "error", "database": "unreachable", "pgvector": None}

    if pgvector_version is None:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "error", "database": "ok", "pgvector": "missing"}

    return {"status": "ok", "database": "ok", "pgvector": pgvector_version}
