"""Synthetic demo data: workspaces, users, CRM customers and tickets. All fictional.

Idempotent: rows are matched by their natural keys (slug, email, external IDs) and only
missing ones are inserted. Used by scripts/seed.py and by the tests.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer, Ticket, User, UserRole, Workspace

WORKSPACES = [
    {"slug": "tasklane-support", "name": "Tasklane Support"},
    {"slug": "acme-demo", "name": "Acme Corp"},
]

USERS = [
    ("tasklane-support", "admin@tasklane.example", "Ava Admin", UserRole.ADMIN),
    ("tasklane-support", "agent@tasklane.example", "Sam Agent", UserRole.AGENT),
    ("tasklane-support", "viewer@tasklane.example", "Vic Viewer", UserRole.VIEWER),
    ("acme-demo", "admin@acme.example", "Ada Acme", UserRole.ADMIN),
    ("acme-demo", "agent@acme.example", "Aki Acme", UserRole.AGENT),
]

# (workspace, external_id, name, plan, status, seats_paid, seats_used, sso, renewal, note)
CUSTOMERS = [
    (
        "tasklane-support",
        "CUST-1001",
        "Brightpath Logistics",
        "pro",
        "suspended",
        40,
        40,
        False,
        date(2026, 10, 15),
        "Renewal card declined on 2026-10-15; retries on days 1, 3 and 5 failed. Grace period "
        "ended 2026-10-22.",
    ),
    (
        "tasklane-support",
        "CUST-1002",
        "Northwind Studio",
        "pro",
        "active",
        15,
        12,
        False,
        date(2027, 3, 1),
        None,
    ),
    (
        "tasklane-support",
        "CUST-1003",
        "Helix Health",
        "enterprise",
        "active",
        250,
        220,
        True,
        date(2027, 1, 31),
        None,
    ),
    ("tasklane-support", "CUST-1004", "Pine & Co", "free", "active", 5, 5, False, None, None),
    (
        "tasklane-support",
        "CUST-1005",
        "Orbit Analytics",
        "pro",
        "past_due",
        30,
        30,
        False,
        date(2026, 11, 2),
        "Payment failed on 2026-11-02 (card expired). Next automatic retry on day 3.",
    ),
    (
        "tasklane-support",
        "CUST-1006",
        "Quarry Labs",
        "enterprise",
        "locked",
        120,
        96,
        True,
        date(2027, 6, 30),
        None,
    ),
    (
        "tasklane-support",
        "CUST-1007",
        "Lumen Retail",
        "pro",
        "active",
        50,
        48,
        False,
        date(2027, 2, 14),
        None,
    ),
    (
        "acme-demo",
        "CUST-9001",
        "Globex Industries",
        "pro",
        "active",
        25,
        20,
        False,
        date(2027, 4, 1),
        None,
    ),
]

# (workspace, customer, external_id, subject, body, status, priority, tags, days_ago)
TICKETS = [
    (
        "tasklane-support",
        "CUST-1001",
        "TCK-2041",
        "Team can't create tasks or upload files",
        "Since yesterday nobody on our team can create tasks or upload files. We can still log in "
        "and see our projects. Our Slack notifications also stopped. What happened?",
        "open",
        "high",
        ["access"],
        1,
    ),
    (
        "tasklane-support",
        "CUST-1001",
        "TCK-1987",
        "Change invoice address",
        "Please update the billing address on our invoices to 12 Harbor Road.",
        "solved",
        "normal",
        ["billing"],
        40,
    ),
    (
        "tasklane-support",
        "CUST-1002",
        "TCK-2050",
        "How do we turn on SSO with Okta?",
        "We want to enforce Okta single sign-on for our members. Where is the setting? We are on "
        "the Pro plan.",
        "open",
        "normal",
        ["sso"],
        2,
    ),
    (
        "tasklane-support",
        "CUST-1003",
        "TCK-2052",
        "SSO-401 errors after certificate rotation",
        "Since this morning our members get error SSO-401 when signing in. Our IT team rotated "
        "the Okta signing certificate last night.",
        "open",
        "urgent",
        ["sso"],
        0,
    ),
    (
        "tasklane-support",
        "CUST-1004",
        "TCK-2047",
        "New member can't sign in",
        "We invited a sixth person and their account shows 'Inactive - seat limit'. Why?",
        "open",
        "normal",
        ["seats"],
        3,
    ),
    (
        "tasklane-support",
        "CUST-1005",
        "TCK-2055",
        "Billing banner shown to owners",
        "All our owners see a red billing banner at the top of the app. Is something wrong?",
        "open",
        "normal",
        ["billing"],
        1,
    ),
    (
        "tasklane-support",
        "CUST-1005",
        "TCK-2056",
        "Refund for annual plan",
        "We bought the annual Pro plan 20 days ago and would like a refund. Your FAQ says 30 days.",
        "open",
        "normal",
        ["billing", "refund"],
        1,
    ),
    (
        "tasklane-support",
        "CUST-1006",
        "TCK-2058",
        "Why is our workspace locked?",
        "Nobody can access our workspace and the page says it is locked. Please tell us why.",
        "open",
        "high",
        ["access"],
        0,
    ),
    (
        "tasklane-support",
        "CUST-1007",
        "TCK-2060",
        "API returns 429 Too Many Requests",
        "Our sync job gets HTTP 429 from the Tasklane API several times per hour. How many "
        "requests can we send?",
        "open",
        "normal",
        ["api"],
        2,
    ),
    (
        "acme-demo",
        "CUST-9001",
        "TCK-9101",
        "Escalation for Globex",
        "Globex needs the escalation contact for a P1 incident.",
        "open",
        "high",
        [],
        1,
    ),
]


def seed(session: Session) -> dict[str, int]:
    """Insert whatever is missing. Returns counts of inserted rows per table."""
    counts = {"workspaces": 0, "users": 0, "customers": 0, "tickets": 0}
    workspaces = {}
    for ws in WORKSPACES:
        workspace = session.scalar(select(Workspace).where(Workspace.slug == ws["slug"]))
        if workspace is None:
            workspace = Workspace(**ws)
            session.add(workspace)
            counts["workspaces"] += 1
        workspace.name = ws["name"]  # keep display names in sync with this file
        workspaces[ws["slug"]] = workspace
    session.flush()

    for slug, email, name, role in USERS:
        if session.scalar(select(User).where(User.email == email)) is None:
            session.add(User(workspace_id=workspaces[slug].id, email=email, name=name, role=role))
            counts["users"] += 1

    customers = {}
    for slug, ext, name, plan, status, paid, used, sso, renewal, note in CUSTOMERS:
        ws_id = workspaces[slug].id
        customer = session.scalar(
            select(Customer).where(Customer.workspace_id == ws_id, Customer.external_id == ext)
        )
        if customer is None:
            customer = Customer(
                workspace_id=ws_id,
                external_id=ext,
                name=name,
                plan=plan,
                account_status=status,
                seats_paid=paid,
                seats_used=used,
                sso_enabled=sso,
                renewal_date=renewal,
                billing_note=note,
            )
            session.add(customer)
            counts["customers"] += 1
        customers[ext] = customer
    session.flush()

    now = datetime.now(UTC)
    for slug, cust, ext, subject, body, status, priority, tags, days_ago in TICKETS:
        ws_id = workspaces[slug].id
        exists = session.scalar(
            select(Ticket).where(Ticket.workspace_id == ws_id, Ticket.external_id == ext)
        )
        if exists is None:
            session.add(
                Ticket(
                    workspace_id=ws_id,
                    customer_id=customers[cust].id,
                    external_id=ext,
                    subject=subject,
                    body=body,
                    status=status,
                    priority=priority,
                    tags=tags,
                    created_at=now - timedelta(days=days_ago, hours=len(ext)),
                )
            )
            counts["tickets"] += 1
    session.flush()
    return counts
