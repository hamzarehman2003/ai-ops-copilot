# RAG Decisions Log

One entry per decision. This is interview prep: be able to defend every line.

## Template

### <Decision title> — <YYYY-MM-DD>
- **Choice:**
- **Alternatives considered:**
- **Why:**
- **Eval evidence:** (run ID, metric before → after)
- **Known trade-offs / when I'd revisit:**

---

### Store document versions with a content hash — 2026-11-03
- **Choice:** `source_documents` (logical doc) → `document_versions` (one per distinct file
  content, SHA-256 `content_hash`, one `is_current` per doc) → `chunks`.
- **Alternatives considered:** a single documents table that is overwritten on re-upload.
- **Why:** identical re-uploads are detected and skipped (no wasted embedding calls); only
  changed files get re-chunked/re-embedded; an answer can cite the exact version it used;
  old versions can be kept for audit and switched off for retrieval.
- **Eval evidence:** n/a (schema decision).
- **Known trade-offs / when I'd revisit:** old versions' chunks take space; may add cleanup.

### Copy `workspace_id` onto every chunk — 2026-11-03
- **Choice:** `chunks.workspace_id` (indexed), even though it is derivable via
  version → document → workspace.
- **Alternatives considered:** join up to `source_documents` at query time.
- **Why:** retrieval must filter by tenant *inside* the vector query (`WHERE workspace_id = :ws
  ORDER BY embedding <=> :q LIMIT k`). No joins in the hot path, and the filter can use an
  index / partial index. Post-filtering after top-k could leak or drop results.
- **Eval evidence:** n/a (security/performance decision).
- **Known trade-offs / when I'd revisit:** denormalized value could drift from the
  document's workspace; ingestion code must set it from the document, never from user input.

### Embedding column deferred to Step 5 — 2026-11-03
- **Choice:** `chunks` has no `embedding vector(N)` column yet.
- **Why:** `N` is fixed by the embedding model (e.g. 384 / 768 / 1536), which is not chosen
  yet. It will be added by its own migration; the HNSW index comes in Step 6.
- **Known trade-offs / when I'd revisit:** changing embedding models later means a new
  column (or table) and re-embedding every chunk; vectors from different models are not
  comparable.

---
