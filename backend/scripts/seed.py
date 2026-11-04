"""Create the demo workspaces, users, customers, and tickets. Safe to run repeatedly.

- tasklane-support: the main tenant (users admin@/agent@/viewer@tasklane.example).
- acme-demo: a second tenant with its own users, customer, and a private document, used to
  prove cross-tenant isolation.

Usage (from backend/):  python -m scripts.seed
"""

from app.db import SessionLocal
from app.seed import seed


def main() -> None:
    with SessionLocal() as session:
        counts = seed(session)
        session.commit()
    print("Inserted:", ", ".join(f"{n} {table}" for table, n in counts.items()))


if __name__ == "__main__":
    main()
