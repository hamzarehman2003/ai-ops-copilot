"""Create the demo workspaces. Safe to run repeatedly.

- tasklane-support: the main tenant; demo docs are uploaded here.
- acme-demo: a second tenant, used later to prove cross-tenant isolation.

Usage (from backend/):  python -m scripts.seed
"""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.db import SessionLocal
from app.models import Workspace

DEMO_WORKSPACES = [
    {"slug": "tasklane-support", "name": "Tasklane Support"},
    {"slug": "acme-demo", "name": "Acme Corp (demo tenant)"},
]


def main() -> None:
    with SessionLocal() as session:
        for ws in DEMO_WORKSPACES:
            inserted_id = session.scalar(
                insert(Workspace)
                .values(**ws)
                .on_conflict_do_nothing(index_elements=["slug"])
                .returning(Workspace.id)
            )
            print(f"{ws['slug']}: {'created' if inserted_id else 'already exists'}")
        session.commit()

        for ws in session.scalars(select(Workspace).order_by(Workspace.slug)):
            print(f"  {ws.slug:<18} {ws.id}")


if __name__ == "__main__":
    main()
