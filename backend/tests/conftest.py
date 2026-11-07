"""Test database setup.

Tests run against a separate database (`<db>_test`), migrated with Alembic, so the dev
database is never touched.

- `session`: a fresh, empty transaction per test, always rolled back.
- `indexed`: a session on a database where the demo data is seeded and every demo document
  is parsed, chunked, embedded and indexed. Indexing happens once per test module (it runs the
  real embedding model); each test then runs in a savepoint that is rolled back.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import URL, Connection, Engine, create_engine, make_url, select, text
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.ingestion.pipeline import process_version
from app.ingestion.upload import register_upload
from app.models import Workspace
from app.seed import seed

BACKEND_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BACKEND_DIR.parent / "data"


def _ensure_database(url: URL) -> None:
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}
        )
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    dev_url = make_url(get_settings().database_url)
    test_url = dev_url.set(database=f"{dev_url.database}_test")
    _ensure_database(test_url)

    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    # '%' must be escaped in ConfigParser values
    rendered = test_url.render_as_string(hide_password=False).replace("%", "%%")
    alembic_cfg.set_main_option("sqlalchemy.url", rendered)
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(test_url)
    yield engine
    engine.dispose()


def _session(conn: Connection) -> Session:
    return Session(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)


@pytest.fixture
def connection(db_engine: Engine) -> Iterator[Connection]:
    with db_engine.connect() as conn:
        outer = conn.begin()
        try:
            yield conn
        finally:
            outer.rollback()


@pytest.fixture
def session(connection: Connection) -> Iterator[Session]:
    """A session whose changes are always rolled back, even if the test commits."""
    sess = _session(connection)
    try:
        yield sess
    finally:
        sess.close()


@pytest.fixture
def session_factory(connection: Connection) -> Callable[[], Session]:
    """More sessions in the same rolled-back transaction (e.g. for background tasks)."""
    return lambda: _session(connection)


# --- Seeded + indexed demo data -------------------------------------------------------------


@dataclass
class Indexed:
    session: Session
    settings: Settings

    def workspace(self, slug: str) -> Workspace:
        return self.session.scalar(select(Workspace).where(Workspace.slug == slug))


@pytest.fixture(scope="module")
def indexed_connection(db_engine: Engine, tmp_path_factory) -> Iterator[tuple]:
    # Tests never call a real model, whatever keys are in .env (LLM tests use fakes).
    settings = Settings(
        upload_dir=tmp_path_factory.mktemp("uploads"), anthropic_api_key=None, llm_api_key=None
    )
    conn = db_engine.connect()
    outer = conn.begin()
    sess = _session(conn)
    seed(sess)
    for folder, slug in (("demo_docs", "tasklane-support"), ("acme_docs", "acme-demo")):
        workspace = sess.scalar(select(Workspace).where(Workspace.slug == slug))
        for path in sorted((DATA_DIR / folder).iterdir()):
            result = register_upload(
                sess, workspace, path.name, path.read_bytes(), settings.upload_dir
            )
            process_version(sess, result.version.id, settings)
    sess.close()
    try:
        yield conn, settings
    finally:
        outer.rollback()
        conn.close()


@pytest.fixture
def indexed(indexed_connection) -> Iterator[Indexed]:
    conn, settings = indexed_connection
    savepoint = conn.begin_nested()
    sess = _session(conn)
    try:
        yield Indexed(sess, settings)
    finally:
        sess.close()
        savepoint.rollback()
