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

### PDF structure from font layout (PyMuPDF) — 2026-11-03
- **Choice:** infer headings from font size relative to the body size (≥ 1.15×) or
  all-bold lines at body size; level = rank of size. Drop running headers/footers (lines in
  the top/bottom 8% repeating on ≥ half the pages, digits ignored) and page numbers.
  Normalize text with NFKC (fixes ligatures like "ﬁ"). Keep char offsets + page ranges.
- **Alternatives considered:** plain `page.get_text()` (loses headings, keeps
  headers/footers); per-page sections (cuts sections at page breaks); layout/ML parsers
  (Unstructured, Docling, LlamaParse: better tables/OCR, heavier dependency).
- **Why:** headings give each chunk context and enable heading-aware chunking; pages give
  citations; removing headers/footers keeps repeated noise out of embeddings.
- **Eval evidence:** demo billing PDF: 9/9 section headings found, header/footer removed,
  section spanning pages 1–2 kept whole (tests/test_pdf_parser.py).
- **Known trade-offs / when I'd revisit:** tables lose row/column structure; scanned PDFs
  rejected (no OCR); multi-column layouts may interleave; documents that mark headings only by
  numbering (same font as body) won't be detected.

### Tables: one self-contained line per row; chunks split only between rows — 2026-11-04
- **Choice:** detect bordered tables with PyMuPDF `find_tables()`, read each cell with
  `get_text(clip=cell)`, drop the original lines inside the table, and insert the table at
  its reading position as rows like `Plan and billing: Pro, annual | Refund window: 14 days
  from purchase or renewal | Refund type: Full refund`. First row is the header if every cell
  is a non-numeric label. `Section.table_spans` marks tables; the chunker uses whole rows as
  pieces inside tables.
- **Alternatives considered:** leave tables as plain text (rows scrambled: before this, "Full
  refund" appeared before "Pro, annual"); `find_tables().extract()` text (drops spaces:
  "Planandbilling"); Markdown tables (chunks from mid-table lose the header); one chunk per
  table always (huge tables exceed the token limit).
- **Why:** a row is the smallest unit that still means something; repeating column names
  makes every row understandable alone, in an embedding or in a chunk.
- **Eval evidence:** demo billing PDF: all 5 rows correct, header detected, no orphan cells
  (tests/test_pdf_parser.py, tests/test_chunking.py). Retrieval impact to measure in Step 9.
- **Known trade-offs / when I'd revisit:** borderless tables aren't detected (fall back to
  plain text); a table continuing on the next page becomes a second, header-less table;
  repeated column names cost tokens; merged cells come through as empty.

### HTML, Markdown, and text parsers — 2026-11-04
- **Choice:** HTML with BeautifulSoup (stdlib `html.parser` backend): read `<main>` /
  `<article>` / `<body>`, drop script/style/nav/aside/forms, page-level header/footer and
  hidden elements (`hidden`, `aria-hidden`, `display:none`); `<h1>`–`<h6>` give the heading
  path; `<li>` keeps "1." / "-" markers; `<th>` decides the table header. Markdown is rendered
  to HTML by markdown-it-py (CommonMark + tables) and goes through the same HTML parser. Plain
  text: underlined lines (`===` level 1, `---` level 2) and short ALL-CAPS lines at a block
  start are headings; separator lines dropped; line breaks inside paragraphs kept.
- **Alternatives considered:** HTML → plain text with `get_text()` (loses headings and tables,
  keeps menus); readability-style boilerplate extraction (trafilatura: better on messy real
  sites, extra dependency, less predictable); Markdown via regexes on `#` lines (breaks on code
  blocks, setext headings, tables); re-flowing text lines into prose (guessing, breaks aligned
  lists); Unstructured for all formats (heavy).
- **Why:** same `ParsedDocument` for every format, so chunking and retrieval don't care about
  the source; one structure walker and one table renderer for HTML and Markdown. Dropping
  hidden HTML matters for security: text readers can't see is a common prompt-injection hiding
  place.
- **Eval evidence:** all 8 demo docs parse with the expected headings, tables, and no
  boilerplate (tests/test_html_parser.py, test_markdown_parser.py, test_text_parser.py), and
  chunk within limits with exact offsets at 300/50 and 60/15 (test_chunking.py).
- **Known trade-offs / when I'd revisit:** colspan/rowspan cells may shift columns; JS-rendered
  pages show only the uploaded HTML; text heading rules are heuristics (a short ALL-CAPS line of
  body text becomes a heading); Markdown soft line breaks become spaces, so stacked
  "**Owner:** x" lines merge into one paragraph; HTML sites without `<main>` keep in-body
  chrome not wrapped in nav/header/footer.

### Section-aware chunking, 300 tokens, 50-token sentence overlap — 2026-11-03
- **Choice:** chunk inside sections only (never across headings); a section that fits in
  300 tokens is one chunk; longer sections are packed sentence by sentence up to 300 tokens,
  and the next chunk starts with up to 50 tokens of whole trailing sentences (overlap).
  Sentences longer than the limit fall back to word splits. Token counts via tiktoken.
- **Alternatives considered:** fixed-size character windows (cuts words/sentences, mixes
  topics across headings); one chunk per page (page breaks are arbitrary); semantic chunking
  with embeddings (more compute, harder to reason about); bigger chunks (500–1000 tokens).
- **Why:** one chunk = one topic with a clear heading path → better embeddings and cleaner
  citations; sentence boundaries keep chunks readable; overlap protects facts that sit on a
  chunk boundary. 300 tokens is a common starting point for FAQ/policy-style docs.
- **Eval evidence:** none yet. To revisit in Step 9 by comparing e.g. 150/300/600 tokens
  on Recall@k.
- **Known trade-offs / when I'd revisit:** overlap is whole sentences, so a sentence longer
  than the overlap budget means no overlap; tiny sections (e.g. "9. Contact", 23 tokens)
  become tiny chunks with little context; sub-chunks after the first don't contain the
  heading text (heading_path is stored and will be prepended when embedding in Step 5);
  "e.g. " / "Inc. " can be mistaken for sentence ends; chunks inherit the whole section's
  page range.

### Embeddings: BAAI/bge-small-en-v1.5 via fastembed, contextual chunk headers — 2026-11-04
- **Choice:** local bge-small-en-v1.5 (384 dims, 512-token input, ONNX/CPU via fastembed, no API
  key), behind an `Embedder` adapter. Embedded text = heading path + chunk; stored `content`
  stays clean. BGE query instruction added to queries only. Model name stored on every chunk.
- **Alternatives considered:** OpenAI `text-embedding-3-small` / Voyage (API: key, cost, data
  leaves the machine); sentence-transformers + PyTorch (+1 GB image); all-MiniLM-L6-v2 (256-token
  limit truncates our 300-token chunks).
- **Why:** runs anywhere with `docker compose up`; the adapter allows comparing an API model later.
- **Eval evidence:** dense-only retrieval, run `20261104T133018Z`: hit@1 0.74, hit@5 0.99,
  MRR 0.85 (95-case set, 73 retrieval-scored). `test_no_chunk_is_truncated_by_the_embedding_model`
  confirms every demo chunk + header fits in 512 BGE tokens.
- **Known trade-offs / when I'd revisit:** weakest single retriever here; compare an API model
  with the same eval; changing models = new column + re-embed.

### Hybrid retrieval (pgvector + Postgres full-text) with RRF — 2026-11-04
- **Choice:** dense (cosine, HNSW, iterative scans) and lexical (`to_tsquery` with OR-ed words,
  `ts_rank_cd`, GIN index on a generated tsvector of headings + content), 20 candidates each,
  fused with Reciprocal Rank Fusion (k = 60). Tenant, current-version, and deprecated filters in
  both SQL queries.
- **Alternatives considered:** dense only; BM25 via an extra engine (Elasticsearch/OpenSearch:
  a second store to sync); weighted score fusion (needs score normalization).
- **Eval evidence** (run `20261104T133018Z`, before deprecation; hit@1 / hit@3 / MRR):
  dense 0.74 / 0.96 / 0.85, lexical 0.86 / 0.97 / 0.91, hybrid 0.81 / 0.96 / 0.89.
  Lexical alone is strong because many questions contain exact terms; hybrid is better than
  dense alone, and fusion matters most once the reranker sits on top (next entry).
- **Known trade-offs / when I'd revisit:** Postgres `ts_rank_cd` is not true BM25; English
  stemming only; OR queries can be noisy on long questions.

### Cross-encoder reranker: ms-marco-MiniLM-L-6-v2 on the top 20 — 2026-11-04
- **Choice:** rerank the best 20 fused candidates with `Xenova/ms-marco-MiniLM-L-6-v2`
  (~80 MB, ONNX/CPU), keep top k = 5.
- **Alternatives considered:** `jina-reranker-v1-turbo-en` (probe: answerable 0.6–1.6 vs
  unanswerable −1.2 to −0.3, overlapping, so no usable threshold); `bge-reranker-base`/`v2-m3`
  (0.5–2 GB); no reranker.
- **Eval evidence:** with the legacy FAQ deprecated (run `20261104T133918Z`): hybrid_rerank
  hit@1 0.93, hit@3 0.99, MRR 0.96 vs hybrid 0.89 / 0.96 / 0.93 and dense 0.89 / 0.97 / 0.93.
  `rerank_top_n` 10 vs 20 (runs `20261104T134359Z` / `20261104T135019Z`): hit@3 0.94 vs 0.97,
  MRR 0.94 vs 0.96, retrieval p50 1324 vs 2223 ms (laptop CPU, other load running: noisy).
- **Known trade-offs / when I'd revisit:** ~1 s+ of CPU per query; weak on vocabulary gaps
  ("money back" vs "refund", case p01); revisit with a GPU, a larger reranker, or query rewriting.

### Abstain threshold: min rerank score −5.0 — 2026-11-04
- **Choice:** chunks with a cross-encoder score below −5 are not given to the answer step; if
  none remain, the copilot abstains (offline) or the LLM sees no documents.
- **Evidence:** probe of 12 answerable + 8 unanswerable questions: answerable top scores 5.6 to
  9.9 except one paraphrase at −4.3; unanswerable −11.3 to +0.6. Eval: correct_abstention 0.64
  (offline mode; 9/14), answered_when_answerable 0.97.
- **Known trade-offs / when I'd revisit:** a threshold can't separate on-topic-but-unanswered
  questions ("smartwatch app?", "uptime SLA?") from answerable ones; that is the LLM's job
  (rerun `--llm`). Recalibrate whenever the reranker changes.

### Deprecated sources filtered inside the query — 2026-11-04
- **Choice:** `source_documents.deprecated`; admins toggle it (`PATCH /api/sources/{id}`,
  audited); retrieval excludes deprecated documents in SQL, like the tenant filter.
- **Eval evidence:** deprecating `legacy-pricing-faq-2024.md` (runs `20261104T133018Z` →
  `20261104T133918Z`): hybrid_rerank hit@1 0.84 → 0.93, MRR 0.91 → 0.96, outdated-ranked-first
  0.50 → 0.00; no_forbidden_claims 0.70 → 1.00.
- **Known trade-offs / when I'd revisit:** needs a human to curate; effective-date metadata +
  freshness boosting would handle partial overlaps automatically.

### Answering: Claude (claude-opus-5-5) with structured output, read-only tools, checks in code
- **Choice:** one provider behind `LLM.turn()`; a manual tool loop (≤ 4 rounds) with two
  read-only `strict` tools; final answer as JSON (`answer`, `citations`, `abstained`,
  `proposed_action`) via `output_config.format`; server-side `fallbacks: "default"` for safety
  refusals. Code validates citations and enforces "cite or abstain"; proposals are validated
  and stored as `pending`. Without an API key: offline mode (cited evidence, no generation).
- **Eval evidence:** offline runs until 2026-11-07; first LLM-mode run `20261107T194616Z`
  (local qwen3.5:9b, judge gemma4:12b): see the faithfulness entry.
- **Known trade-offs / when I'd revisit:** effort `medium` not yet tuned; no prompt caching
  (prompt below the cacheable minimum).

### Faithfulness: claim-level LLM judge, a different model than the answerer — 2026-11-07
- **Choice:** `evals/judge.py` splits each non-abstained answer into atomic claims and marks
  each supported or not by the context the model was given (chunks + tool results);
  faithfulness = supported / claims, averaged. The judge sees only sources + answer, sources
  are escaped and marked as data, and it runs after all answers (one model swap on a 12 GB
  GPU). Answerer qwen3.5:9b, judge gemma4:12b (both local, free).
- **Alternatives:** RAGAS (same idea, extra dependency and its own prompts); NLI model per
  (sentence, chunk) pair (cheaper, weaker on paraphrase); a single "grounded? yes/no" judge
  (hides partial hallucinations, not actionable).
- **Eval evidence:** run `20261107T194616Z`: faithfulness 0.97 over 74 answers, 0 judge errors.
  Unsupported claims are listed per case in the report (e.g. inferring "suspended" from a date
  instead of a tool result).
- **Known trade-offs / when I'd revisit:** the judge is a 12B model: some "unsupported" claims
  are meta statements it shouldn't have extracted; spot-check failures, and calibrate against
  ~30 human labels before trusting small differences.

### Follow-ups are searched with the previous question — 2026-11-07
- **Choice:** in a conversation, retrieval searches `previous question + "\n" + question`
  (`retrieval/query.py`, setting `retrieval_follow_up_context`); the model still sees the
  user's exact question. `[S#]`/`[T#]` markers are removed from history (ids are per turn,
  and the model was copying stale ones).
- **Alternatives:** LLM query rewrite into a standalone question (better with pronouns and
  topic switches, but +1 model call per follow-up and nothing in offline mode); retrieving
  separately for both and fusing (more candidates to rerank).
- **Eval evidence:** 8 new `follow_up` cases (f01–f08), offline, legacy FAQ deprecated.
  Off (`--out` scratch run `20261107T184204Z`): follow-up MRR 0.81 (f04 missed entirely);
  on (`20261107T184530Z`): follow-up MRR 1.00; all 103 cases: hybrid_rerank MRR
  0.942 → 0.962, hit@1 0.91 → 0.94.
- **Known trade-offs / when I'd revisit:** a topic switch ("what about SSO?" after a refund
  question) still drags the old topic into the search; the reranker usually sorts it out, but
  an LLM rewrite is the fix if multi-turn cases show it.

### Tool results are citable sources ([T#]); no "any tool call" pass — 2026-11-07
- **Choice:** each successful tool result gets a `source_id` (`T1`, `T2`...) in what the model
  sees; answers cite it like a document. "Cite or abstain" now requires at least one valid
  `[S#]` or `[T#]`; before, any successful tool call let an uncited answer through. Unknown
  markers are also removed from the answer text, not only from `citations`. Prompt v2 also
  marks tool output (ticket text) as untrusted, like documents.
- **Why:** review finding: with a customer selected, the model could look up the account and
  then answer a policy question from memory, uncited, and pass the check.
- **Eval evidence:** offline run `20261107T183538Z` vs `20261104T135019Z`: every answer and
  retrieval metric unchanged (expected: offline answers only gain a `[T1]`). Local
  qwen3.5:9b spot check (5 demo scenarios): the account answers cite `[T1]`, and no new
  abstentions. LLM-mode numbers: see the faithfulness entry once it lands.
- **Known trade-offs / when I'd revisit:** a citation is still only checked to exist, not to
  support its sentence (that needs an NLI model or an LLM judge).

### Embedding column deferred to Step 5 — 2026-11-03
- **Choice:** `chunks` has no `embedding vector(N)` column yet.
- **Why:** `N` is fixed by the embedding model (e.g. 384 / 768 / 1536), which is not chosen
  yet. It will be added by its own migration; the HNSW index comes in Step 6.
- **Known trade-offs / when I'd revisit:** changing embedding models later means a new
  column (or table) and re-embedding every chunk; vectors from different models are not
  comparable.

---
