"""PDF parser: body text and heading structure from born-digital PDFs.

A PDF has no "heading" or "paragraph" tags, only positioned text with fonts. So structure
is inferred from layout:

1. Read every text line with its font size, boldness, page, and vertical position.
   Tables are detected first; their cells are read row by row and the table becomes one
   item (one line per row), replacing the scrambled lines that were inside it.
2. Drop running headers/footers: lines inside the top/bottom margin that repeat on most
   pages (ignoring digits), and bare page numbers ("Page 3 of 9").
3. The body font size is the size used by the most characters.
4. A line is a heading if it is noticeably larger than body text, or if it is entirely bold
   at body size and short. Heading level = rank of its size (largest = level 1).
5. Walk the lines in reading order: each heading starts a new section; body text goes into
   the current section. Sections may span pages.

Out of scope for now:
- Tables without drawn borders (PyMuPDF's default detection needs ruling lines), and
  tables continuing on the next page (the second part is read as a new table).
- Scanned PDFs (no text layer): rejected with ParseError; would need OCR.
- Multi-column layouts: reading order may interleave columns.
"""

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import groupby

import pymupdf

from app.ingestion.parsing.base import (
    ParsedDocument,
    ParseError,
    SectionDraft,
    assemble_document,
    normalize_line,
    render_table,
)

MARGIN_RATIO = 0.08  # top/bottom 8% of the page is where running headers/footers live
REPEATED_ON_PAGES_RATIO = 0.5  # header/footer if it appears on at least half the pages
HEADING_SIZE_RATIO = 1.15  # 15% larger than body text -> heading
MAX_HEADING_CHARS = 120
BOLD_FLAG = 1 << 4  # PyMuPDF span flag bit for bold
TABLE_BLOCK_START = 100_000  # block numbers for tables, so they never merge with text blocks

PAGE_NUMBER = re.compile(r"^(page\s*)?\d+(\s*(of|/)\s*\d+)?$", re.IGNORECASE)
SENTENCE_END = (".", "!", "?", ":", ";")


@dataclass
class Line:
    text: str
    size: float  # font size of the line's main span, rounded
    bold: bool  # every visible span is bold
    page: int  # 1-based
    block: int  # PyMuPDF block number within the page (roughly: a paragraph)
    in_margin: bool  # entirely inside the top or bottom margin
    y0: float  # top of the line on the page
    is_table: bool = False  # a whole table, already rendered one row per line


def parse_pdf(data: bytes) -> ParsedDocument:
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except (RuntimeError, ValueError) as exc:  # pymupdf.FileDataError is a RuntimeError
        raise ParseError("Could not open PDF (corrupt or not a PDF)") from exc

    with doc:
        if doc.needs_pass:
            raise ParseError("PDF is password-protected")

        lines = _read_lines(doc)
        if not lines:
            raise ParseError("PDF has no text layer (scanned?). OCR is not supported yet.")

        lines = _drop_headers_and_footers(lines, doc.page_count)
        body_size = _body_font_size(lines)
        drafts = _build_sections(lines, body_size)
        title = _pick_title(doc.metadata, drafts)
        return assemble_document(title, drafts, page_count=doc.page_count)


# --- 1. Reading lines ------------------------------------------------------------------


def _read_lines(doc: pymupdf.Document) -> list[Line]:
    lines: list[Line] = []
    for page in doc:
        tables = _read_tables(page)
        # Lines inside a table are dropped: the table comes back as one clean item instead.
        page_lines = [
            line
            for line, center in _read_page_lines(page)
            if not any(center in rect for rect, _ in tables)
        ]
        lines.extend(_insert_tables(page_lines, tables, page.number + 1))
    return lines


def _read_page_lines(page: pymupdf.Page) -> list[tuple[Line, pymupdf.Point]]:
    """All text lines of a page, each with its center point (used to test "inside a table")."""
    top = page.rect.height * MARGIN_RATIO
    bottom = page.rect.height * (1 - MARGIN_RATIO)
    result = []
    # sort=True orders blocks top-to-bottom, left-to-right (reading order for 1 column)
    for block_no, block in enumerate(page.get_text("dict", sort=True)["blocks"]):
        if block["type"] != 0:  # 1 = image
            continue
        for raw in block["lines"]:
            spans = [s for s in raw["spans"] if s["text"].strip()]
            text = normalize_line("".join(s["text"] for s in raw["spans"]))
            if not spans or not text:
                continue
            main_span = max(spans, key=lambda s: len(s["text"].strip()))
            bbox = pymupdf.Rect(raw["bbox"])
            line = Line(
                text=text,
                size=round(main_span["size"], 1),
                bold=all(_is_bold(s) for s in spans),
                page=page.number + 1,
                block=block_no,
                in_margin=bbox.y1 <= top or bbox.y0 >= bottom,
                y0=bbox.y0,
            )
            center = pymupdf.Point((bbox.x0 + bbox.x1) / 2, (bbox.y0 + bbox.y1) / 2)
            result.append((line, center))
    return result


def _is_bold(span: dict) -> bool:
    return bool(span["flags"] & BOLD_FLAG) or "bold" in span["font"].lower()


# --- 1b. Tables ----------------------------------------------------------------------------


def _read_tables(page: pymupdf.Page) -> list[tuple[pymupdf.Rect, str]]:
    """Find tables on the page and render each one as text (one line per row).

    find_tables() is only used for the cell positions: its own text extraction drops spaces
    between words, so each cell's text is read separately with get_text(clip=cell).
    """
    tables = []
    for table in page.find_tables().tables:
        rows = [[_cell_text(page, cell) for cell in row.cells] for row in table.rows]
        text = render_table(rows)
        if text:
            tables.append((pymupdf.Rect(table.bbox), text))
    return tables


def _cell_text(page: pymupdf.Page, bbox: tuple | None) -> str:
    if bbox is None:  # part of a merged cell
        return ""
    return normalize_line(page.get_text("text", clip=pymupdf.Rect(bbox)))


def _insert_tables(
    lines: list[Line], tables: list[tuple[pymupdf.Rect, str]], page: int
) -> list[Line]:
    """Put each table at its reading position: before the first line below its top edge."""
    result = list(lines)
    for index, (rect, text) in enumerate(tables):
        table_line = Line(
            text=text,
            size=0.0,
            bold=False,
            page=page,
            block=TABLE_BLOCK_START + index,
            in_margin=False,
            y0=rect.y0,
            is_table=True,
        )
        position = next((i for i, ln in enumerate(result) if ln.y0 >= rect.y0), len(result))
        result.insert(position, table_line)
    return result


# --- 2. Running headers and footers ------------------------------------------------------


def _drop_headers_and_footers(lines: list[Line], page_count: int) -> list[Line]:
    def key(text: str) -> str:
        # "Page 1 of 9" and "Page 2 of 9" are the same running footer
        return re.sub(r"\d+", "#", text.lower())

    pages_by_key: dict[str, set[int]] = defaultdict(set)
    for line in lines:
        if line.in_margin:
            pages_by_key[key(line.text)].add(line.page)

    min_pages = max(2, math.ceil(page_count * REPEATED_ON_PAGES_RATIO))
    repeated = {k for k, pages in pages_by_key.items() if len(pages) >= min_pages}

    return [
        line
        for line in lines
        if not (line.in_margin and (key(line.text) in repeated or PAGE_NUMBER.match(line.text)))
    ]


# --- 3. Body font size ---------------------------------------------------------------------


def _body_font_size(lines: list[Line]) -> float:
    chars_per_size: Counter[float] = Counter()
    for line in lines:
        if not line.is_table:
            chars_per_size[line.size] += len(line.text)
    if not chars_per_size:  # a document that is only tables
        return 0.0
    return chars_per_size.most_common(1)[0][0]


# --- 4. Headings ---------------------------------------------------------------------------


def _heading_rank(line: Line, body_size: float) -> float | None:
    """A sortable "importance" for heading lines (bigger = higher level), None for body text."""
    if line.is_table or len(line.text) > MAX_HEADING_CHARS:
        return None
    if line.size >= body_size * HEADING_SIZE_RATIO:
        return line.size
    # Bold at body size counts too, but not smaller bold text (e.g. table header cells)
    # and not bold sentences.
    if line.bold and line.size >= body_size - 0.5 and not line.text.endswith(SENTENCE_END):
        return body_size
    return None


# --- 5. Sections ---------------------------------------------------------------------------


def _build_sections(lines: list[Line], body_size: float) -> list[SectionDraft]:
    ranks = {id(line): _heading_rank(line, body_size) for line in lines}
    distinct_ranks = sorted({r for r in ranks.values() if r is not None}, reverse=True)
    level_of = {rank: level for level, rank in enumerate(distinct_ranks, start=1)}

    drafts: list[SectionDraft] = []
    stack: list[str] = []  # current heading path
    current = SectionDraft(heading=None, heading_path=[])

    # Process one PyMuPDF block at a time; consecutive lines of the same kind in a block
    # form one heading (wrapped over several lines) or one paragraph.
    for (page, _block), block_lines in groupby(lines, key=lambda ln: (ln.page, ln.block)):
        for rank, run_iter in groupby(block_lines, key=lambda ln: ranks[id(ln)]):
            run = list(run_iter)
            run_text = _join_lines([ln.text for ln in run])

            if run[0].is_table:  # a table is always its own block: keep it as one paragraph
                current.page_start = current.page_start or page
                current.table_indices.add(len(current.paragraphs))
                current.paragraphs.append(run_text)
                current.page_end = page
                continue

            if rank is not None:
                drafts.append(current)
                level = level_of[rank]
                stack = stack[: level - 1] + [run_text]
                current = SectionDraft(
                    heading=run_text, heading_path=list(stack), page_start=page, page_end=page
                )
                continue

            if current.page_start is None:
                current.page_start = page
            if _continues_previous(current, run_text, page):
                current.paragraphs[-1] += " " + run_text
            else:
                current.paragraphs.append(run_text)
            current.page_end = page

    drafts.append(current)
    return drafts


def _join_lines(texts: list[str]) -> str:
    """Join wrapped lines into one string, undoing end-of-line hyphenation ("pay-\\nment")."""
    joined = texts[0]
    for text in texts[1:]:
        if joined.endswith("-") and text[:1].islower():
            joined = joined[:-1] + text
        else:
            joined += " " + text
    return joined


def _continues_previous(current: SectionDraft, text: str, page: int) -> bool:
    """A paragraph cut by a page break: previous one has no sentence end, this starts lowercase."""
    return (
        bool(current.paragraphs)
        and len(current.paragraphs) - 1 not in current.table_indices
        and current.page_end is not None
        and page > current.page_end
        and not current.paragraphs[-1].endswith(SENTENCE_END)
        and text[:1].islower()
    )


def _pick_title(metadata: dict | None, drafts: list[SectionDraft]) -> str | None:
    title = normalize_line((metadata or {}).get("title") or "")
    if title:
        return title
    for draft in drafts:
        if draft.heading_path:
            return draft.heading_path[0]
    return None
