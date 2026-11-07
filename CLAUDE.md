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
- **Keep [docs/interview-prep.md](docs/interview-prep.md) growing:** whenever an explanation
  or a new step raises an interview-worthy question, add it (question → short answer →
  "In this repo" pointer) under the matching topic section, or a new section for a new topic.

## Stack

- Frontend: Next.js + React + TypeScript + Tailwind (`frontend/`, port 3002)
- Backend: Python 3.12, FastAPI, Pydantic, SQLAlchemy 2 (sync) + psycopg 3, Alembic (`backend/`)
- DB: PostgreSQL + pgvector (one vector store only)
- LLM: small adapter (`generation/llm.py`), two backends: Anthropic Claude, or any
  OpenAI-compatible API (Gemini, Ollama, Groq, OpenAI) chosen by `LLM_PROVIDER`; structured
  outputs + tool calling. The copilot loop and all checks are provider-independent
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
    ingestion/            upload -> parse -> chunk -> embed -> index (pipeline.py)
    retrieval/            dense + lexical -> RRF -> cross-encoder rerank -> threshold
    generation/           prompt, LLM adapters (Claude / OpenAI-compatible), copilot loop, grounding checks
    tools/                read-only tool registry (authz, timeouts, retries), mock CRM, actions
    seed.py               synthetic workspaces/users/customers/tickets
  scripts/                one-off scripts (e.g. build_demo_pdf.py)
  tests/
frontend/                 Next.js dashboard: Overview (/), Copilot, Sources, Search lab, Approvals,
                          Audit log, Evaluations. shadcn/ui (radix-nova) in components/ui/ (add more
                          with `npx shadcn@4.22.1 add <name>`, then pin any new deps exactly); theme
                          variables (deep teal, light + dark) in app/globals.css; app-level wrappers
                          (PageHeader, Panel, StatTile, StatusBadge...) in components/ui.tsx;
                          Playwright smoke tests in tests/
evals/                    cases.jsonl (103 cases) + run_eval.py + results/ (source of truth for metrics)
data/demo_docs/           synthetic docs; see data/README.md for what each file tests
data/acme_docs/           a second tenant's private doc (cross-tenant leak tests)
infra/db/init.sql         enables pgvector on a fresh DB volume
docs/                     spec, architecture, rag-decisions, interview-prep
```

## Commands

<!-- Keep these accurate; Claude relies on them. -->
Host ports: Postgres **5433**, API **8001** (5432/8000 are used by other local projects).

- Start stack: `docker compose up -d --build` (from repo root)
  (compose builds the backend's `dev` image target: dev deps, bind mount, `--reload`; the
  default `runtime` target is the production-shaped image: `docker build -t ops-copilot-api backend`)
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
- Seed demo workspaces, users, customers, tickets (idempotent):
  `docker compose exec api python -m scripts.seed`
- Upload + index all demo docs via the API, waits until ready (idempotent; reindexes
  never-processed duplicates): `docker compose exec api python -m scripts.upload_demo_docs`
- Frontend: `cd frontend && npm install && npm run dev` (http://localhost:3002, proxies `/api`
  to `API_URL`, default http://localhost:8001)
- API docs / manual testing: http://localhost:8001/docs
- See what the parser extracts from a file (from `backend/`):
  `.venv/Scripts/python -m scripts.parse_file ../data/demo_docs/billing-and-refunds-policy.pdf [--full]`
  (In Git Bash, prefix Docker commands that take `/data/...` paths with `MSYS_NO_PATHCONV=1`.)
- See the chunks for a file: `.venv/Scripts/python -m scripts.chunk_file <file> [--max-tokens 60 --overlap 15]`
- Tests use a separate `copilot_test` database (created + migrated automatically by
  `tests/conftest.py`); each test is rolled back.
- Evals (needs seeded + indexed dev DB; runs in a rolled-back transaction):
  `cd backend && .venv/Scripts/python ../evals/run_eval.py [--deprecate legacy-pricing-faq-2024.md] [--llm]`
  or `docker compose exec api python /evals/run_eval.py`. Writes `evals/results/<run>.json`,
  `latest.json`, and a per-case CSV. `--llm` calls the real model (costs money).
- Embedding/reranker models download on first use to `backend/.cache/models` (Docker: `models`
  volume). The first test run downloads them (~150 MB).
- LLM: set `ANTHROPIC_API_KEY` in `.env`, or `LLM_PROVIDER=openai` + `LLM_BASE_URL` +
  `LLM_API_KEY` + `LLM_MODEL` for Gemini (free tier) / Ollama / Groq (see `.env.example`);
  without a key the copilot runs in offline mode. Tests never call a real model
  (`conftest.py` clears the keys; adapter tests use a mocked transport, `test_llm_openai.py`).
  Free tiers have small per-model daily quotas: `LLM_FALLBACK_MODELS` (comma-separated) are
  tried when the model is out of quota/overloaded; exhausted models are skipped until reset.
  Local Ollama (`qwen3.5:9b`): needs `LLM_SCHEMA_WITH_TOOLS=false` (its JSON-schema mode
  blocks tool calls), `LLM_EFFORT=none`, `LLM_TEMPERATURE=0.3`; see `.env.example`.
- Reset the demo before a recording/rehearsal (clears conversations, actions, CRM changes,
  deprecated flags, docs uploaded during the demo; keeps users + indexed demo docs):
  `docker compose exec api python -m scripts.reset_demo --yes` (logic in `app/demo_reset.py`).

## API (so far)

All `/api/*` routes (except `/api/users`) need header `X-User: <email>` of a seeded user
(`admin@`, `agent@`, `viewer@tasklane.example`; `admin@`/`agent@acme.example`). **Temporary**
stand-in for auth, resolved only in `get_current_user` (`app/deps.py`) and only while
`DEMO_AUTH=true` (off: every call 401, `/api/users` 404); workspace and role come
from that user. Roles via `require_role`: admin = sources; admin/agent = approve/reject.

- Sources: `POST /api/sources` (admin; 201 new / 200 duplicate / 400 / 413 / 415; processing
  starts in the background), `GET /api/sources[/{id}]`, `PATCH /api/sources/{id}`
  `{deprecated}`, `POST /api/sources/{id}/reindex`, `GET /api/sources/{id}/chunks`.
- Copilot: `POST /api/copilot/query` `{question, customer_id?, conversation_id?}`,
  `POST /api/copilot/query/stream` (same body; Server-Sent Events: `progress` steps, then one
  `result` with the /query body; the Copilot page uses this),
  `POST /api/copilot/messages/{id}/feedback`, `GET /api/copilot/messages/{id}/trace`,
  `GET /api/search?q=&mode=&k=` (retrieval only).
- CRM/actions: `GET /api/customers`, `GET /api/customers/{id}/tickets`,
  `GET /api/actions?status=`, `POST /api/actions/{id}/approve|reject|retry`, `GET /api/audit-events`.
- Meta: `GET /api/me`, `GET /api/users`, `GET /api/meta`, `GET /api/evaluations/latest`.
- Other workspaces' rows are always 404 (tenant condition inside the query).

Upload logic lives in `app/ingestion/upload.py` (no FastAPI). Files are stored under
`UPLOAD_DIR` at `{workspace}/{document}/v{n}-{hash12}{ext}`; DB stores the relative path.
A new version stays `pending` and `is_current=false` until `process_version`
(`ingestion/pipeline.py`) succeeds and swaps it in within the same transaction, so retrieval
never reads a half-processed version.

## Parsing

`app/ingestion/parsing/`: one parser per format, all returning `ParsedDocument`
(`title`, `text`, `sections` with `heading_path`, `char_start/char_end`, `page_start/page_end`;
invariant: `doc.text[s.char_start:s.char_end] == s.text`). `parse(source_type, bytes)` dispatches.
All four types are done:
- **PDF** (`pdf.py`): headings from font size/bold, bordered tables, header/footer removal; no OCR.
- **HTML** (`html.py`, BeautifulSoup): reads `<main>`/`<article>`/`<body>`; drops script/style/
  nav/aside/forms, page-level header/footer, and hidden elements; `<h1>`–`<h6>` → sections.
- **Markdown** (`markdown.py`): markdown-it-py renders to HTML, then the HTML parser runs.
- **Text** (`text.py`): underlined (`===`/`---`) and ALL-CAPS lines are headings; line breaks kept.

Shared helpers in `parsing/base.py`: `decode_text` (UTF-8, `\n` endings), `SectionBuilder`
(heading-level stack), `render_table` (one line per row repeating column names; recorded in
`Section.table_spans`).

## Chunking

`app/ingestion/chunking.py`: `chunk_document(doc, max_tokens=300, overlap_tokens=50)` →
`ChunkDraft`s. Chunks never cross sections; long sections split at sentence boundaries
(whole rows inside tables, words for giant sentences); overlap is whole pieces. Tokens counted with tiktoken
`cl100k_base` (`app/ingestion/tokens.py`). Format-agnostic: works on any `ParsedDocument`
(`test_every_demo_doc_chunks_cleanly` covers all demo files).

## Embeddings, retrieval, answering

- Embeddings: `app/ingestion/embeddings.py` (bge-small-en-v1.5, 384 dims, fastembed; embeds
  `heading path + chunk`; BGE query prefix on queries only).
- Retrieval: `app/retrieval/search.py`, modes dense | lexical | hybrid | hybrid_rerank (default);
  tenant/current/deprecated filters inside SQL; writes `retrieval_traces`. Tuning in `config.py`
  (`retrieval_k=5`, `retrieval_candidates=20`, `rerank_top_n=20`, `min_rerank_score=-5`).
- Copilot: `app/generation/copilot.py` (`ask`): retrieval → LLM tool loop or offline → grounding
  checks → optional pending `ProposedAction`. Prompt in `generation/prompts.py`
  (`PROMPT_VERSION`); bump it on every prompt change and re-run evals.
- Tests: `tests/conftest.py` `indexed` fixture seeds and indexes all demo docs once per module
  (real models); LLM behaviour is tested with a scripted `FakeLLM` (`tests/test_copilot.py`).

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
