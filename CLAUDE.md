# AI Operations Copilot

Demo/portfolio project: a support copilot for a fictional B2B SaaS company. It answers questions
with RAG over docs + tickets, calls read-only account tools, and proposes write actions that only
run after human approval. Full spec: [docs/spec.md](docs/spec.md).

**Primary goal of this repo is learning RAG deeply** (for interviews), not shipping fast.

## Working agreement (learning split)

- **Claude writes:** UI, CRUD endpoints, Pydantic schemas, migrations, Docker, mock CRM API,
  auth scaffolding, synthetic data, Playwright tests.
- **I write, Claude teaches/reviews:** anything in `packages/retrieval/`, `services/ingestion/`
  chunking/embedding logic, the grounded-answer prompt, and `evals/` metrics.
  In these areas: explain trade-offs and alternatives first, leave `TODO(human)` for core logic,
  and review my code rather than rewriting it. Don't write the core logic unless I ask.
- Every non-trivial RAG decision (chunk size, embedding model, k, threshold, hybrid weighting,
  reranker) gets an entry in [docs/rag-decisions.md](docs/rag-decisions.md) with eval evidence.

## Stack

- Frontend: Next.js + React + TypeScript + Tailwind (`apps/web/`)
- Backend: Python, FastAPI, Pydantic, SQLAlchemy, Alembic (`services/api/`)
- DB: PostgreSQL + pgvector (one vector store only)
- LLM: one provider behind a small adapter; structured outputs + tool calling
- No LangGraph / agent framework for v1: approval is a state column on `ProposedAction`
- Ingestion runs via FastAPI `BackgroundTasks` (no separate worker for v1)
- Tracing: our own `RetrievalTrace` / `ToolCall` tables first; Langfuse optional later
- Everything runs via Docker Compose

## Layout

```
apps/web/                 Next.js dashboard (chat, citations, sources, pending actions, evals)
services/api/             FastAPI app, auth, tool registry, approval/action service
services/ingestion/       parse -> normalize -> chunk -> embed -> index
packages/retrieval/       query, metadata filtering, vector/hybrid search, ranking
packages/tool_registry/   typed tool schemas, authz, timeouts, allow-list
evals/                    cases.jsonl + run_eval.py (source of truth for metrics)
data/demo_docs/           synthetic docs, policies, FAQs, tickets
docs/                     spec, architecture, rag-decisions
```

## Commands

<!-- Fill in as each piece exists. Keep these accurate; Claude relies on them. -->
- Start stack: `docker compose up -d` (TBD)
- Backend tests: `pytest` (TBD)
- Lint: `ruff check . && ruff format --check .` (TBD)
- Migrations: `alembic upgrade head` (TBD)
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
