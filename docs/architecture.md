# Architecture

```
 Browser (Next.js, :3002)
   │  /api/* (rewritten to the API)          header X-User: <email>  (temporary auth stand-in)
   ▼
 FastAPI (:8001) ─────────────────────────────────────────────────────────────────────────
   routers/        sources · copilot · crm (customers, actions, audit) · meta
   ingestion/      upload → parse → chunk → embed → index      (BackgroundTasks)
   retrieval/      dense + lexical → RRF → cross-encoder rerank → threshold
   generation/     prompt · LLM adapters (Claude / OpenAI-compatible) · copilot orchestration · grounding checks
   tools/          read-only tool registry · mock CRM · proposed actions (approve → execute)
   ▼
 PostgreSQL 17 + pgvector  (one store for documents, vectors, CRM data, traces, audit)
```

## Ingestion (`app/ingestion/`)

1. `POST /api/sources` (admin): validate type + content, SHA-256, store bytes, create a
   `pending` version (duplicates return 200 and do nothing).
2. Background task `process_version`: parse (`parsing/`, one parser per format → `ParsedDocument`)
   → `chunk_document` (300 tokens, 50 overlap, never crosses sections, tables split by rows)
   → embed `heading path + chunk` (bge-small, 384 dims) → insert chunks → swap `is_current`
   in the same transaction. Failures mark the version `failed` and keep the old one serving.
3. Postgres keeps `search_vector` (tsvector of headings + content) up to date itself.

## Retrieval (`app/retrieval/search.py`)

```
question ─┬─ embed (BGE query prefix) ─ ORDER BY embedding <=> q LIMIT 20 ─┐
          └─ to_tsquery(word | word …) ─ ORDER BY ts_rank_cd LIMIT 20 ─────┴─ RRF ─ top 20
                                                     ─ cross-encoder ─ score ≥ −5 ─ top 5
```
Both SQL queries filter `workspace_id`, `is_current`, and `deprecated` inside the query.
Every query writes a `retrieval_traces` row (all candidates with dense/lexical rank, RRF, rerank).

## Answering (`app/generation/copilot.py`)

1. Store the user message; retrieve (scoped to the caller's workspace).
2. Build the prompt: system rules + escaped `<document id="S1">` blocks + selected customer.
3. Tool loop (≤ 4 rounds): the model may call `get_account_status` / `get_recent_tickets`;
   `tools/registry.py` authorizes each call against the human-selected customer and workspace,
   applies timeout + retries, validates the response, and records a `tool_calls` row.
4. Final structured answer → code checks: citations must refer to a retrieved document
   (`[S#]`) or a successful tool result of this run (`[T#]`); unknown markers are removed from
   the text; no valid citation → abstain; a proposed action (never on an abstention) is
   validated (allow-listed type,
   payload rules, ticket belongs to this customer) and stored as `pending`.
5. Without an API key (or if the LLM fails): offline mode, same steps 1–4 without generation.

The loop speaks Anthropic's message shape. `LLM_PROVIDER=openai` swaps in `OpenAICompatLLM`
(`generation/llm.py`), which translates each turn to Chat Completions (tools → functions,
answer schema → `response_format`, `tool_result` blocks → `tool` messages) and sends assistant
turns back verbatim (Gemini's tool-call thought signatures must round-trip). Rate limits and
5xx are retried with backoff; timeouts fall back to offline mode. A 429 that asks to wait
longer than 30 s (a daily quota) is not retried: the turn moves to the next of
`LLM_FALLBACK_MODELS`, and the exhausted model is skipped until its reset.

Local models (Ollama): a JSON schema in `response_format` turns on grammar-constrained decoding,
which leaves the model no way to emit a tool call (it answers without checking the account).
With `LLM_SCHEMA_WITH_TOOLS=false`, tool turns go out without the schema; if the model answers
instead of calling a tool and its reply is not already the JSON answer, the turn is re-sent
once with the schema and no tools. When a small model emits two tool calls in one turn that the
server can't parse (Ollama returns HTTP 500 "expected element type <function>"), the adapter
re-sends that turn offering one tool at a time, unused tools first, instead of retrying the
same request (which fails the same way). The demo machine (RTX 3060, 12 GB) runs `qwen3.5:9b` with
thinking off and temperature 0.3. In a 2026-11-07 scenario comparison it handled the tool
calls, injection and abstention cases; gemma4:12b timed out or returned unparseable JSON, and
qwen3:14b skipped tools and spilled onto the CPU. Thinking on doubled to quadrupled latency
without making tool use more reliable.

Live progress: `ask(..., on_progress=...)` reports steps (retrieving, retrieved, model round,
tool, tool_done, checking). `POST /api/copilot/query/stream` runs `ask` in a worker thread and
relays the steps as Server-Sent Events, then sends the final body. Authorization (customer
scope) happens before the stream starts. The response sets `Cache-Control: no-transform` so
the Next.js proxy doesn't gzip (and buffer) it.

## Actions (`app/tools/actions.py`)

`pending → approved → executed | failed`, or `pending → rejected`. Approve/reject need role
admin or agent (`require_role`), the row is locked `FOR UPDATE`, the executor refuses anything
not approved, and the mock CRM applies writes idempotently (`crm_operations`). Every step writes
an `audit_events` row. Any execution error (not only CRM errors) ends in `failed`, never stuck
in `approved`; `POST /api/actions/{id}/retry` re-runs a failed or stuck approved action with
its original approval and idempotency key, so a write that already landed is replayed, not
applied twice.

## Security rules and where they live

| Rule | Enforced in |
|---|---|
| Tenant isolation | every query filters `workspace_id` from `get_current_user` (`deps.py`); 404 across tenants |
| Customer scope for tools | `_authorize` in `tools/registry.py` (selected customer + workspace) |
| Roles | `require_role` (`deps.py`): upload/reindex/deprecate = admin; approve = admin/agent |
| Retrieved text is data | escaped, delimited prompt; no write tools; proposals validated in code |
| No write without approval | `execute_action` status gate + approval endpoint + row lock |
| Never fabricate | `_enforce_grounding` (cite or abstain); account facts only from tool results |
| Tool robustness | timeouts, bounded retries, idempotency keys, response validation (`tools/`) |

## Data model (`app/models.py`)

Knowledge: `workspaces → source_documents → document_versions → chunks (embedding, search_vector)`.
Mock CRM: `customers → tickets → ticket_notes`, `crm_operations` (idempotency).
Runs and audit: `users`, `conversations → messages`, `retrieval_traces`, `tool_calls`,
`proposed_actions`, `audit_events`.
