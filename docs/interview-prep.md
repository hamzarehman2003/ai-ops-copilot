# RAG Interview Prep

Questions that came up while building this project, with short answers I should be able to
give from memory. Each answer points to where it lives in this repo.

**Format:** question → short answer → *In this repo* pointer. Newest topics at the bottom.

---

## 1. Vector database

### Why pgvector instead of a dedicated vector DB (Pinecone, Qdrant, Weaviate)?
One database for everything: chunks sit next to documents, versions, and permissions, so
there is nothing to sync. Tenant filtering is a plain `WHERE` clause, hybrid search can use
Postgres full-text search, and re-indexing is transactional. Dedicated vector DBs make sense
at very large scale (tens–hundreds of millions of vectors) or with a team to operate them.
*In this repo:* `docker-compose.yml` (`pgvector/pgvector:pg17`), `docs/rag-decisions.md`.

### What is the difference between exact and approximate nearest-neighbour search?
Exact search compares the query with every vector: always correct, slow at scale.
Approximate (ANN) indexes like HNSW and IVFFlat are much faster but may miss a few true
nearest neighbours. You trade a little recall for a lot of speed.

### HNSW vs IVFFlat?
- **HNSW:** graph-based; better speed/recall trade-off, no training step, can be built on an
  empty table; uses more memory and builds slower. Tuned with `m`, `ef_construction`,
  `ef_search`.
- **IVFFlat:** clusters vectors into lists; builds faster, less memory; must be built after
  data exists; tuned with `lists` and `probes`.

### What goes wrong when you combine an ANN index with a metadata filter?
The index finds the k nearest vectors first, then the `WHERE` filter removes the ones from
other tenants, so you can get fewer than k results (or none). Fixes: iterative index scans
(pgvector 0.8+), a partial index per tenant, or partitioning by tenant.

---

## 2. Data model

### Why do we need database tables for RAG at all?
In pgvector, the "vector DB" *is* a table. Chunks and embeddings must be stored to be
searchable; metadata (page, heading, version) makes citations possible; documents/versions
track uploads and re-indexing; `workspace_id` keeps tenants apart.
*In this repo:* `backend/app/models.py`.

### Why store document versions with a content hash?
Re-uploading identical bytes is detected and skipped (no wasted embedding calls); only
changed files are re-processed; an answer can cite the exact version it used; old versions can
be kept for audit but excluded from retrieval.
*In this repo:* `DocumentVersion.content_hash`, unique `(document_id, content_hash)`.

### Why copy `workspace_id` onto every chunk when it can be derived via joins?
So retrieval can filter by tenant *inside* the vector query
(`WHERE workspace_id = :ws ORDER BY embedding <=> :q LIMIT k`) with no joins in the hot path.
Filtering *after* top-k can leak data or drop results. Trade-off: the value must be set by
ingestion code from the document, never from user input.

### Do you store the chunk text, the embedding, or both?
Both, in the same row. The embedding is only for *finding* chunks: you can't turn a vector back
into text. The text is needed to put in the LLM prompt, show citations, run keyword/full-text
search (hybrid), and re-embed everything when you change embedding models. Same row means the
text and its vector can't get out of sync, and one query does filter + search + return text.
Note: the text you embed can differ from the text you store (e.g. heading path prepended for
embedding, clean content stored for display).
*In this repo:* `Chunk.content` + metadata now; `Chunk.embedding` added in Step 5.

### Why wasn't the embedding column created up front?
Its dimension is fixed by the embedding model (384 / 768 / 1536...). Changing models later
means a new column (or table) and re-embedding everything: vectors from different models are
not comparable.

---

## 3. Upload / ingestion

### How do you avoid re-embedding a file that hasn't changed?
Hash the file bytes (SHA-256). If the same document already has a version with that hash,
return it as a duplicate and do nothing else.
*In this repo:* `backend/app/ingestion/upload.py` → `register_upload`.

### Why validate file content and not just the extension?
The extension is user-controlled and proves nothing. Check the bytes: PDFs start with
`%PDF-`, text formats must decode as UTF-8. Reject mismatches with 415.

### Why not use the uploaded filename in the storage path?
Path traversal (`../../etc/x`). Keep only the base name for display, and build storage paths
from generated IDs: `{workspace}/{document}/v{n}-{hash}{ext}`.

### Cross-tenant access: 403 or 404?
404. A 403 confirms the resource exists; 404 reveals nothing. Put the tenant condition in the
query itself so another tenant's row is simply "not found".

### Why isn't a newly uploaded version immediately "current"?
Retrieval would see a half-processed version (no or partial chunks). The new version is swapped
in only after processing succeeds, so the old one keeps serving until then.

### Is checking file size in the API handler enough?
No. By the time the handler runs, the framework has already received the body. Enforce a hard
request-size limit at the reverse proxy too (e.g. nginx `client_max_body_size`).

---

## 4. Parsing

### Why one parser per file type?
Each format stores text differently (PDF: positioned text with fonts; HTML: tags; Markdown:
symbols; TXT: nothing). All parsers return the same `ParsedDocument`, so chunking and
everything after never cares about the source format. Adding `.docx` = one new parser + one
line in the registry (adapter/strategy pattern).
*In this repo:* `backend/app/ingestion/parsing/__init__.py` (`PARSERS`, `parse()`).

### Why keep structure (headings, pages, offsets) instead of just plain text?
Headings give chunks context; pages enable citations ("page 1"); character offsets let the UI
highlight the exact cited passage; cleaning keeps headers/footers/nav out of embeddings.

### How do you detect headings in a PDF?
PDFs have no heading tags, only text with fonts and positions. Find the body font size (the size
used by the most characters); a line is a heading if it is clearly larger (≥ 1.15×) or fully
bold at body size and short. Heading level = rank of its font size.
*In this repo:* `backend/app/ingestion/parsing/pdf.py` → `_body_font_size`, `_heading_rank`.

### How do you remove running headers and footers from PDFs?
Lines inside the top/bottom margin that repeat on most pages (comparing with digits ignored, so
"Page 1 of 9" = "Page 2 of 9") are dropped, plus bare page numbers.
*In this repo:* `_drop_headers_and_footers` in `pdf.py`.

### PDF text extraction gives you lines. Why is that a problem?
A PDF stores visual lines, not sentences or paragraphs: one sentence can be split across lines
(and across pages). Rebuild paragraphs before chunking (here: join lines in the same layout
block, undo end-of-line hyphenation), or chunks can cut sentences in half.
*In this repo:* `_build_sections` and `_join_lines` in `pdf.py`.

### What is text normalization and why does it matter for search?
PDFs often contain ligatures ("ﬁ" as one character), non-breaking spaces, soft hyphens. If not
normalized, a search for "file" won't match "ﬁle". Unicode NFKC normalization fixes these.
*In this repo:* `normalize_line` in `parsing/base.py`.

### How do you handle tables in RAG?
Plain text extraction loses table structure: a PDF table is just positioned text, so rows and
columns disappear, and rows with wrapped cells can come out in the wrong order (a value lands
next to the wrong row). Retrieval still finds the chunk, but the LLM reads jumbled facts.
Fix: detect tables (e.g. PyMuPDF `page.find_tables()`), convert them to a structured form
(Markdown table, or one line per row that repeats the column names:
`Plan: Pro, annual | Refund window: 14 days | Refund type: Full refund`), exclude the table
area from normal text extraction, and chunk tables separately: whole table if small, otherwise
by rows with the header row repeated in every chunk.
*In this repo:* `_read_tables` in `parsing/pdf.py` (uses `find_tables()` only for cell
positions, then reads each cell with `get_text(clip=cell)`, because `find_tables`' own text
drops spaces), `render_table` in `parsing/base.py`, `Section.table_spans`; the chunker
splits tables between rows only (`_pieces` in `chunking.py`). Before/after: section 4 of the
demo billing PDF.

### Why render table rows as "Column: value | Column: value" instead of a Markdown table?
Each row becomes self-contained: if a big table is split across chunks, every row still
carries its column names, so there's no need to repeat a header row per chunk, and an
embedding of a single row still knows what each value means. Markdown tables are more compact
and read well for an LLM, but a chunk from the middle of a Markdown table has rows with no
header. Trade-off: repeating column names costs extra tokens.

### Which tables are hard to extract from PDFs?
Tables without drawn borders (detection relies on ruling lines; text-alignment detection is
noisy), tables continuing onto the next page (the second part has no header), merged cells,
nested tables, and tables in scanned PDFs (need OCR + layout models).

### How would you detect tables that have no borders?
Ruling-line detection finds nothing, so use text alignment instead: words that line up in the
same x-positions across several lines form columns (PyMuPDF `find_tables(strategy="text")`,
pdfplumber/Camelot "stream" mode). It is noisy: multi-column layouts, aligned lists and forms
also look like tables. So use it only as a **fallback** when the lines strategy finds nothing,
and keep a candidate only if it passes sanity checks (≥ 2 columns, ≥ 3 rows, most cells filled,
consistent column count). Heavier options: layout models (Docling's TableFormer, Unstructured
`hi_res`) or a vision LLM on the page image. Cheapest fix of all: ingest the HTML/Markdown
source when you have it, where tables are explicit (`<table>`, `|` pipes).
*In this repo:* not done yet; PDF tables are detected with ruling lines only (`_read_tables`).

### How do you handle a table that continues onto the next page?
Merge the two parts before rendering. Treat the table at the top of page N+1 as a continuation
if the previous page ended with a table (nothing but the footer below it), there is no heading
or text between them, and both have the same column count and roughly the same column
x-positions. If the first row of the second part repeats the header, drop it; either way, give
its rows the first part's header. Keep the raw cell rows until the merge, then render once.
*In this repo:* not done yet (known limit in `docs/rag-decisions.md`).

### Repeating column names in every table row costs tokens. How do you reduce that?
First measure: on the demo table, row form is 127 tokens vs 93 for a Markdown table (~37% more).
Options: (1) accept it for small/medium tables (self-contained rows help embeddings);
(2) store a compact Markdown table and repeat the header **once per chunk** instead of once
per row, by adding the header at embed/prompt time (like a contextual chunk header), so stored
offsets stay exact; (3) separate texts: embed row form, show the LLM compact Markdown. The cost
mainly hurts wide tables with long headers and short values (e.g. numbers).
*In this repo:* `render_table` in `parsing/base.py` uses row form for now.

### How do you extract clean text from HTML pages?
Don't use the whole page's text: menus, footers, cookie banners and scripts end up in chunks
and pollute embeddings ("boilerplate"). Read the main content (`<main>`, `<article>`), drop
`<script>`, `<style>`, `<nav>`, `<aside>`, forms, site-level header/footer, and use the tags
for structure: `<h1>`–`<h6>` for the heading path, `<li>` for list items, `<table>` for rows.
For messy real-world sites, readability-style extractors (trafilatura, readability-lxml) score
blocks by text density to guess the main content.
*In this repo:* `backend/app/ingestion/parsing/html.py`.

### Why drop hidden HTML elements when indexing?
Users never see them, so they add nothing true for answers, and they are a classic place to
hide prompt-injection text ("ignore previous instructions...") in a page that looks harmless.
Dropping `hidden`, `aria-hidden="true"`, and `display:none` content shrinks that attack
surface. It's only one layer: visible text can still contain injections, so retrieved content
is always treated as untrusted data in the prompt.
*In this repo:* `_is_hidden` in `parsing/html.py`; rule 3 in `CLAUDE.md`.

### How do you parse Markdown for RAG?
Use a real Markdown parser, not regexes on `#` lines: `#` inside a code block isn't a heading,
headings can also be underlined (`===`), and tables need parsing. Here markdown-it-py renders
Markdown to HTML and the HTML parser handles it: one code path for structure and tables, and
inline syntax (`**bold**`, links) disappears instead of ending up in embeddings. Also strip YAML
front matter.
*In this repo:* `backend/app/ingestion/parsing/markdown.py`.

### How do you find structure in plain-text files?
There is no markup, so use writing conventions as heuristics: lines underlined with `===`/`---`,
short ALL-CAPS lines on their own, separator lines, blank lines between paragraphs. Keep the
rules conservative: a wrong heading is copied as context onto every chunk of its section.
User-written text (e.g. forum posts) should not be promoted to headings easily.
*In this repo:* `backend/app/ingestion/parsing/text.py`.

### Does chunking need to change per file format?
No, if every parser returns the same structure (sections with heading paths, text, offsets,
table spans). Format-specific work stays in the parser; the chunker is format-agnostic. That's
the payoff of a common intermediate representation.
*In this repo:* `ParsedDocument` in `parsing/base.py`; `test_every_demo_doc_chunks_cleanly`.

### What are the hard cases in PDF parsing?
Tables (row/column structure lost in plain extraction; handled here for bordered tables),
scanned PDFs (no text layer → need OCR), multi-column layouts (reading order interleaves),
headings that differ only by numbering.
Heavier tools (Unstructured, Docling, LlamaParse) handle more of these.

---

## 5. Chunking

### Why chunk documents at all?
Embedding models have token limits, and a small, focused chunk produces a more precise
embedding than a whole document. Smaller chunks also make citations more specific.

### Why measure chunk size in tokens rather than characters?
Model limits and costs are in tokens, and the characters-per-token ratio varies with the text.
*In this repo:* `backend/app/ingestion/tokens.py` (tiktoken `cl100k_base`).

### Where does "token cost" show up in a RAG pipeline?
1. **Embedding:** every chunk is embedded once at ingestion (paid per token for API models,
   compute time for local ones), and again whenever you re-embed.
2. **LLM prompt:** the top-k retrieved chunks are sent with *every* question, so extra tokens in
   chunks are paid on every query and use up the context window. This is usually the largest.
3. **Chunk budget:** chunks have a token limit, so wordier text = fewer facts per chunk = more
   chunks to store, search and retrieve.
Also a quality cost: text repeated in many chunks (boilerplate, column names) makes their
embeddings more alike and harder to tell apart.
*In this repo:* `count_tokens` in `ingestion/tokens.py`; table row form vs Markdown (127 vs 93
tokens on the demo table).

### Why never let a chunk cross a section (heading) boundary?
One chunk = one topic with one heading path → cleaner embeddings and citations. Mixing two
sections blends two topics into one vector.
*In this repo:* `chunk_document` / `split_section` in `backend/app/ingestion/chunking.py`.

### Why split at sentence boundaries?
Fixed-size cuts break words and sentences, which hurts embeddings and makes chunks unreadable
in citations.

### What is chunk overlap and why use it?
Consecutive chunks share some text (here ~50 tokens of whole sentences), so a fact that sits on
a chunk boundary still appears complete in at least one chunk. Trade-off: some duplicate text
gets stored and embedded. Here overlap is whole sentences, so a sentence longer than the
overlap budget means no overlap at that boundary.

### How do you choose the chunk size?
Start with a common default (~200–500 tokens for FAQ/policy text; here 300), then **measure**:
run the retrieval eval (Recall@k) with several sizes and keep the best. Small chunks = precise
but little context; large chunks = more context but diluted embeddings and noisier citations.

### How do chunks keep their link to the heading they came from?
1. The parser assigns every paragraph to the nearest heading above it (heading path stack).
2. The chunker never mixes sections and copies `heading_path` onto every chunk.
3. When embedding, prepend the heading path to the chunk text ("contextual chunk headers"), so
   chunks from the middle of a section still carry their topic. The stored content stays clean
   for display.
*In this repo:* `_build_sections` in `pdf.py`; `_make_chunk` in `chunking.py`; Step 5.

---

## 6. Embeddings

### What is an embedding?
A list of numbers (a vector, e.g. 384 or 1536 of them) that represents the *meaning* of a text.
Texts with similar meaning get vectors that point in similar directions, so "Can I get my money
back?" lands close to "Refund eligibility" even with no words in common. Closeness is usually
measured with cosine similarity (pgvector: `<=>` is cosine *distance*).

### How do you choose an embedding model?
Trade-offs: retrieval quality on *your* data (measure with your eval set; public leaderboards
like MTEB are only a starting point), max input tokens (longer chunks get truncated), vector
size (storage and search speed), cost and latency, local vs API (privacy, no network, no key vs
no hardware to run), and language support. Keep it behind an adapter so you can swap and compare.

### What happens if a chunk is longer than the model's max input?
Most models silently truncate: the end of the chunk is never embedded, so facts there can't be
found by vector search. Keep chunk size + contextual header under the model's limit, and count
with the model's own tokenizer (different tokenizers count differently).

### Why must queries and documents use the same embedding model?
Each model has its own vector space; vectors from two models (or two versions) are not
comparable. Store the model name with the vectors, and re-embed everything when you switch.

### What kinds of embeddings are there?
- **Dense** (one vector per text, e.g. 384–3072 numbers): captures meaning and paraphrases. The
  default for RAG. Weak on exact rare strings (error codes, IDs, names).
- **Sparse** (one weight per vocabulary word, mostly zeros): BM25 (classic, not learned) or
  SPLADE (learned). Great at exact terms, weaker on paraphrases.
- **Multi-vector / late interaction** (ColBERT: one vector per token, scored with MaxSim):
  higher quality, but many times the storage.
Production systems often combine dense + sparse (**hybrid search**) and add a reranker.

### How much storage do embeddings need, and how do you reduce it?
`chunks × dimensions × 4 bytes` (float32), plus index overhead (HNSW likes to fit in RAM).
1M chunks × 1536 dims ≈ 6.1 GB; at 384 dims ≈ 1.5 GB. Reduce with fewer dimensions (models
trained "Matryoshka"-style can be truncated), half precision (pgvector `halfvec`), int8 or binary
quantization (re-rank the top results with full vectors to recover quality).

### How do you switch embedding models in production without downtime?
Like a blue/green deploy: add a new column/table for the new model, backfill embeddings in the
background, compare both on the eval set, switch queries to the new one, then drop the old one.
Store the model name + version with every vector. API models get deprecated, which forces this.

### Are embeddings sensitive data?
Yes. Embedding-inversion attacks can reconstruct much of the original text from a vector, so
protect vectors like the text itself: same tenant filters, encryption, retention, and access
rules. Sending text to an embedding API is sending customer data to a third party (check DPA,
data retention, region).

### What do you watch in a production embedding pipeline?
Quality on your own eval set; model version per vector; truncation (chunk + header under the
limit, counted with the model's tokenizer); query vs document prefixes / `input_type`; matching
distance metric and normalization; batching, rate limits, retries, idempotency, and a queue (not
the request path) for bulk indexing; cost (dedupe by content hash, cache query embeddings);
query-time latency and a fallback (e.g. keyword search) if the embedding API is down; storage
and RAM for the index; tenant filtering inside the query; monitoring for latency, errors, and
empty or low-score results.
