"""Shared FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_session
from app.models import Workspace

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_current_workspace(
    session: SessionDep, x_workspace: Annotated[str, Header(description="Workspace slug")]
) -> Workspace:
    """Resolve the caller's workspace (tenant).

    TEMPORARY: trusts the `X-Workspace` header. Real authentication will replace only this
    function; every route already scopes its queries to the workspace returned here.
    """
    workspace = session.scalar(select(Workspace).where(Workspace.slug == x_workspace))
    if workspace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    return workspace


WorkspaceDep = Annotated[Workspace, Depends(get_current_workspace)]
