# AI Operations Copilot

Demo/portfolio project: a support copilot for a fictional B2B SaaS company. It answers questions
with RAG over docs + tickets, calls read-only account tools, and proposes write actions that only
run after human approval. Full spec: [docs/spec.md](docs/spec.md).

**Primary goal of this repo is learning RAG deeply** (for interviews), not shipping fast.

## Working agreement (learning split)

- **Claude writes:** UI, CRUD endpoints, Pydantic schemas, migrations, Docker, mock CRM API,
  auth scaffolding, synthetic data, Playwright tests.
- **I write, Claude teaches/reviews:** anything in `backend/app/retrieval/`, the parsing/chunking/
  embedding logic in `backend/app/ingestion/`, the grounded-answer prompt, and `evals/` metrics.
  In these areas: explain trade-offs and alternatives first, leave `TODO(human)` for core logic,
  and review my code rather than rewriting it. Don't write the core logic unless I ask.
- Every non-trivial RAG decision (chunk size, embedding model, k, threshold, hybrid weighting,
  reranker) gets an entry in [docs/rag-decisions.md](docs/rag-decisions.md) with eval evidence.

## Stack

- Frontend: Next.js + React + TypeScript + Tailwind (`frontend/`, not started)
- Backend: Python 3.12, FastAPI, Pydantic, SQLAlchemy 2 (sync) + psycopg 3, Alembic (`backend/`)
- DB: PostgreSQL + pgvector (one vector store only)
- LLM: one provider behind a small adapter; structured outputs + tool calling
- No LangGraph / agent framework for v1: approval is a state column on `ProposedAction`
- Ingestion runs via FastAPI `BackgroundTasks` (no separate worker for v1)
- Tracing: our own `RetrievalTrace` / `ToolCall` tables first; Langfuse optional later
- Everything runs via Docker Compose

## Layout

One Python project (`backend/`) with subpackages, instead of the spec's separate
services/packages: simpler imports and one venv for a demo.

```
backend/
  app/
    main.py, config.py, db.py
    routers/              FastAPI routes (health, sources, copilot, actions...)
    ingestion/            parse -> normalize -> chunk -> embed -> index   (planned)
    retrieval/            metadata filtering, vector/hybrid search, ranking (planned)
    generation/           LLM adapter, grounded answers, citations          (planned)
    tools/                typed tool schemas, authz, timeouts, allow-list   (planned)
  scripts/                one-off scripts (e.g. build_demo_pdf.py)
  tests/
frontend/                 Next.js dashboard (planned)
evals/                    cases.jsonl + run_eval.py (source of truth for metrics)
data/demo_docs/           synthetic docs; see data/README.md for what each file tests
infra/db/init.sql         enables pgvector on a fresh DB volume
docs/                     spec, architecture, rag-decisions
```

## Commands

<!-- Keep these accurate; Claude relies on them. -->
Host ports: Postgres **5433**, API **8001** (5432/8000 are used by other local projects).

- Start stack: `docker compose up -d --build` (from repo root)
- DB only: `docker compose up -d db`
- Health check: `curl http://localhost:8001/health`
- Dependencies: pinned in `backend/requirements.txt` (runtime) and `requirements-dev.txt`
  (pytest, ruff, ...). Add new packages there with an exact version; `pyproject.toml` is tool
  config only.
- Local venv: `backend/.venv` (`cd backend && .venv/Scripts/python -m pip install -r requirements-dev.txt`)
- Backend tests (DB must be up): `cd backend && .venv/Scripts/python -m pytest`
  or inside Docker: `docker compose exec api pytest`
- Lint: `cd backend && .venv/Scripts/ruff check . && .venv/Scripts/ruff format --check .`
- Regenerate demo PDF: `cd backend && .venv/Scripts/python scripts/build_demo_pdf.py`
- Migrations run automatically on `api` container start. Manually (from `backend/`):
  `.venv/Scripts/alembic upgrade head`; new migration after editing `app/models.py`:
  `.venv/Scripts/alembic revision --autogenerate --rev-id 000N -m "what changed"`, then **review
  the generated file**; `.venv/Scripts/alembic check` confirms models and DB match.
- Seed demo workspaces (idempotent): `docker compose exec api python -m scripts.seed`
- Tests use a separate `copilot_test` database (created + migrated automatically by
  `tests/conftest.py`); each test is rolled back.
- Evals: `python evals/run_eval.py` (TBD)

## Non-negotiable rules

1. **Authorization is enforced in backend code**, never by prompt wording or UI hiding.
2. **Tenant/customer scope is applied as a filter inside the retrieval query and every tool**:
   never post-filter results after the fact, and never trust a customer ID chosen by the LLM
   without checking it against the caller's permissions.
3. **Retrieved content is untrusted data.** It is passed to the model as clearly delimited
   context and can never change tool policy, permissions, or system instructions.
4. **No write action executes without an approved `ProposedAction` record.** The executor
   checks approval status server-side.
5. **Never fabricate.** Account status comes only from tool results; "action succeeded" only
   when the tool confirms it. Answers cite evidence or explicitly abstain.
6. Tools have timeouts, bounded retries, and idempotency keys.
7. Synthetic data only. No real customer data, no secrets in the repo (`.env` is gitignored;
   keep `.env.example` updated).
8. Don't invent performance numbers. Metrics come from `evals/run_eval.py` runs, which record
   model, prompt, and index versions.

## Conventions

- Work in small slices: one module/endpoint per change, with tests.
- Plan before implementing anything touching retrieval, authz, or the action executor.
- Any change to chunking, retrieval, or prompts: re-run evals and note the before/after.
