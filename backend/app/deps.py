"""Shared FastAPI dependencies: database session, settings, and the current user."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config import Settings, get_settings
from app.db import SessionLocal, get_session
from app.models import User, UserRole, Workspace

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_session_factory() -> Callable[[], Session]:
    """Sessions for work that outlives the request (background ingestion). Overridden in tests."""
    return SessionLocal


SessionFactoryDep = Annotated[Callable[[], Session], Depends(get_session_factory)]


def get_current_user(
    session: SessionDep,
    x_user: Annotated[str | None, Header(description="Email of a seeded demo user")] = None,
) -> User:
    """Resolve the caller.

    TEMPORARY stand-in for real authentication (e.g. OIDC/SSO): it trusts the `X-User`
    header. Only this function changes when real auth arrives; every route already takes
    the workspace and role from the User it returns, never from the request body.
    """
    if not x_user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing X-User header")
    user = session.scalar(
        select(User).where(User.email == x_user.lower()).options(joinedload(User.workspace))
    )
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown user")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_current_workspace(user: CurrentUser) -> Workspace:
    """The caller's tenant. Every query must be scoped to it."""
    return user.workspace


WorkspaceDep = Annotated[Workspace, Depends(get_current_workspace)]


def require_role(*roles: UserRole) -> Callable[[User], User]:
    """Route dependency: 403 unless the caller has one of `roles` (checked server-side)."""

    def check(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"Requires role: {', '.join(r.value for r in roles)}"
            )
        return user

    return check


AdminUser = Annotated[User, Depends(require_role(UserRole.ADMIN))]
ApproverUser = Annotated[User, Depends(require_role(UserRole.ADMIN, UserRole.AGENT))]
