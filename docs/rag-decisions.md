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

### Embedding column deferred to Step 5 — 2026-11-03
- **Choice:** `chunks` has no `embedding vector(N)` column yet.
- **Why:** `N` is fixed by the embedding model (e.g. 384 / 768 / 1536), which is not chosen
  yet. It will be added by its own migration; the HNSW index comes in Step 6.
- **Known trade-offs / when I'd revisit:** changing embedding models later means a new
  column (or table) and re-embedding every chunk; vectors from different models are not
  comparable.

---
