# AI Operations Copilot

A support copilot for a fictional B2B SaaS company ("Tasklane"). A support agent asks about a
customer's problem; the copilot retrieves product docs (RAG), checks the customer's account
through read-only tools, drafts a cited answer (or abstains), and proposes a ticket action that
only runs after a human approves it. Everything is synthetic, and every metric below comes from
`evals/run_eval.py`.

**Stack:** FastAPI · PostgreSQL 17 + pgvector · SQLAlchemy/Alembic · fastembed (bge-small,
MiniLM cross-encoder) · LLM adapter: Claude (`claude-opus-5-5`) or any OpenAI-compatible API, e.g. Gemini, Ollama (optional) · Next.js + Tailwind · Docker Compose

## What it does

| Area | Implementation |
|---|---|
| Ingestion | PDF (headings from font layout, tables, header/footer removal), HTML (boilerplate and hidden-element removal), Markdown, text → section-aware 300-token chunks → embeddings → pgvector. Versioned by SHA-256; new versions swap in atomically after indexing. |
| Retrieval | Dense (HNSW, cosine) + Postgres full-text, fused with RRF, reranked by a cross-encoder, thresholded for abstention. Tenant, current-version, and deprecated filters inside the SQL. Every query traced. |
| Answers | Claude or any OpenAI-compatible model (Gemini, Ollama, Groq, OpenAI) with structured output and two read-only tools; code checks citations ("cite or abstain"). Offline mode (no API key): same pipeline, cited evidence instead of generation. |
| Tools and actions | Customer-scoped tool authorization, timeouts, bounded retries, response validation; proposed ticket notes/tags/status changes → human approve/edit/reject → idempotent execution against a mock CRM; full audit log. |
| Evals | 95 labeled cases: retrieval per mode, abstention, citations, required/forbidden facts, cross-tenant leaks, injection, role checks, tool faults. |

## Quick start

```bash
cp .env.example .env            # optional LLM: Anthropic key, Gemini/Groq/OpenAI key, or a local Ollama model (otherwise offline mode)
docker compose up -d --build    # db :5433, api :8001, web :3002
docker compose exec api python -m scripts.seed               # users, customers, tickets
docker compose exec api python -m scripts.upload_demo_docs   # upload + index, waits until ready
```

Open http://localhost:3002 (UI) or http://localhost:8001/docs (API). There is no real login:
pick a demo user in the top bar (`admin@`, `agent@`, `viewer@tasklane.example`, or the second
tenant `admin@`/`agent@acme.example`). API calls send it as the `X-User` header.

## Demo script

Before each take: `docker compose exec api python -m scripts.reset_demo --yes` (fresh
conversations, approvals, tickets; indexed docs are kept). In LLM mode the Copilot shows each
step live (search → account tools → model rounds → checks).

1. **Copilot**, customer *Brightpath Logistics*: "Why can't the team create tasks or upload
   files?" → account status `suspended` from the CRM tool + the suspension policy, cited.
2. Follow up: "Add an internal note to their open ticket summarizing why they're blocked." →
   the copilot reads the tickets and proposes a note on TCK-2041 (LLM mode; larger hosted
   models often propose it unprompted). Approve it → executed, and in the **Audit log**.
3. *Northwind Studio*: "Can we turn on SSO with Okta?" → Pro plan, SSO is Enterprise-only.
4. "What is the capital of France?" → abstains instead of guessing.
5. Switch to `agent@acme.example` and search "ORCHID-7" → found; as a Tasklane user → nothing
   (tenant isolation). A Tasklane user can't query Acme's customer (404).
6. **Sources**: mark `legacy-pricing-faq-2024.md` deprecated → conflict questions stop citing it.
7. **Search lab**: compare dense / lexical / hybrid / hybrid+rerank on "SSO-409".
8. **Evaluations**: the latest report.

## Evaluation results

Offline answer mode (no LLM), 95 cases, 73 scored for retrieval, k = 5, laptop CPU.
Reports: `evals/results/`. Reproduce: `docker compose exec api python /evals/run_eval.py
--deprecate legacy-pricing-faq-2024.md`.

| Retrieval (legacy FAQ deprecated, run `20261104T135019Z`) | hit@1 | hit@3 | MRR |
|---|---|---|---|
| dense (bge-small) | 0.89 | 0.97 | 0.93 |
| lexical (Postgres FTS) | 0.86 | 0.97 | 0.91 |
| hybrid (RRF) | 0.89 | 0.96 | 0.93 |
| **hybrid + rerank** (default) | **0.93** | **0.97** | **0.96** |

- Deprecating the outdated FAQ: hybrid+rerank hit@1 0.84 → 0.93, outdated source ranked first
  in conflict questions 50% → 0% (runs `20261104T133018Z` → `20261104T133918Z`).
- Security checks: 0 cross-tenant leaks, 0 tool calls outside the selected customer, 0 actions
  executed without approval, 3/3 HTTP role/tenant checks enforced, 0 injections followed.
- Tool faults (timeout, 503, malformed response): 3/3 handled without inventing account facts.
- Offline abstention accuracy 0.64 (9/14): a score threshold can't tell "on-topic but not in the
  docs" apart; that's the LLM's job. LLM-mode numbers: run with `--llm` (not yet recorded).
- Retrieval latency p50 ≈ 2.2 s on CPU, mostly the cross-encoder (top 10 instead of 20:
  1.3 s, hit@3 0.97 → 0.94).

Design decisions with evidence: [docs/rag-decisions.md](docs/rag-decisions.md).
Architecture: [docs/architecture.md](docs/architecture.md).
Interview notes: [docs/interview-prep.md](docs/interview-prep.md).

## Development

```bash
cd backend
python -m venv .venv && .venv/Scripts/python -m pip install -r requirements-dev.txt
docker compose up -d db
.venv/Scripts/alembic upgrade head
.venv/Scripts/python -m pytest           # 157 tests; first run downloads the models
.venv/Scripts/ruff check . && .venv/Scripts/ruff format --check .
cd ../frontend && npm install && npm run dev   # http://localhost:3002
```

## Limitations

- Auth is a stand-in (`X-User` header); replace `get_current_user` with real OIDC/SSO.
- Ingestion runs in FastAPI BackgroundTasks; production needs a queue and workers.
- The mock CRM is in-process; faults are simulated.
- PDF: no OCR, borderless tables not detected, multi-column layouts may interleave.
- Reranking on CPU is slow (~1–2 s); weak on vocabulary gaps ("money back" vs "refund").
- English-only stemming and models. Small corpus: numbers will move with more documents.
