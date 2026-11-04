"""The common output of every parser, plus helpers shared by all formats.

Each file type has its own parser, but all of them return a `ParsedDocument`, so chunking
(Step 4) and everything after it never needs to know where the text came from.
"""

import re
import unicodedata
from dataclasses import dataclass, field

SECTION_SEPARATOR = "\n\n"
PARAGRAPH_SEPARATOR = "\n\n"


class ParseError(Exception):
    """The file could not be turned into text (corrupt, encrypted, scanned, ...)."""


@dataclass
class Section:
    """A heading and the text under it, up to the next heading."""

    heading_path: list[str]  # e.g. ["Billing and Refund Policy", "4. Refund eligibility"]
    text: str  # heading line + paragraphs, paragraphs separated by a blank line
    char_start: int  # offsets into ParsedDocument.text: text == doc.text[char_start:char_end]
    char_end: int
    page_start: int | None = None  # 1-based; PDFs only
    page_end: int | None = None
    # Where tables sit inside `text` (offsets relative to the section). Each table is one
    # row per line, so the chunker can split between rows but never inside a row.
    table_spans: list[tuple[int, int]] = field(default_factory=list)


@dataclass
class ParsedDocument:
    title: str | None
    text: str  # the whole normalized document; sections are slices of it
    sections: list[Section]
    page_count: int | None = None


@dataclass
class SectionDraft:
    """A section being built by a parser, before offsets are known."""

    heading: str | None
    heading_path: list[str]
    paragraphs: list[str] = field(default_factory=list)
    page_start: int | None = None
    page_end: int | None = None
    table_indices: set[int] = field(default_factory=set)  # which paragraphs are tables


_WHITESPACE = re.compile(r"\s+")
_NUMBER_LIKE = re.compile(r"[\d\s.,%$€£+-]+")


def decode_text(data: bytes) -> str:
    """Bytes of a text format (Markdown, HTML, TXT) -> str with Unix line endings."""
    try:
        text = data.decode("utf-8-sig")  # -sig: drop a byte-order mark if there is one
    except UnicodeDecodeError as exc:
        raise ParseError("File is not valid UTF-8 text") from exc
    return text.replace("\r\n", "\n").replace("\r", "\n")


def normalize_line(text: str) -> str:
    """Make extracted text consistent so that search matches what users type.

    NFKC turns compatibility characters into plain ones: the PDF ligature 'ﬁ' -> 'fi',
    non-breaking space -> space, full-width letters -> ASCII. Soft hyphens are invisible
    and removed. Runs of whitespace collapse to one space.
    """
    text = unicodedata.normalize("NFKC", text).replace("­", "")
    return _WHITESPACE.sub(" ", text).strip()


def render_table(rows: list[list[str]], header: bool | None = None) -> str:
    """Turn table cells into text that keeps its meaning after chunking.

    With a header row, every data row becomes one self-contained line that repeats the
    column names:
        Plan and billing: Pro, annual | Refund window: 14 days | Refund type: Full refund
    So a row still makes sense on its own, even if the table is split across chunks.
    Without a header row, cells are joined with " | ". Empty cells are skipped.

    `header`: True/False when the format says so (HTML <th>), None to guess (PDF).
    """
    rows = [[normalize_line(cell or "") for cell in row] for row in rows]
    rows = [row for row in rows if any(row)]
    if not rows:
        return ""

    if header is None:
        header = _looks_like_header(rows)
    if header and len(rows) >= 2:
        names, body = rows[0], rows[1:]
        lines = [
            " | ".join(
                f"{name}: {value}" if name else value
                for name, value in zip(names, row, strict=False)
                if value
            )
            for row in body
        ]
    else:
        lines = [" | ".join(cell for cell in row if cell) for row in rows]
    return "\n".join(line for line in lines if line)


def _looks_like_header(rows: list[list[str]]) -> bool:
    """First row is a header if there are data rows below it and every cell is a label."""
    first = rows[0]
    return len(rows) >= 2 and all(first) and not any(_NUMBER_LIKE.fullmatch(c) for c in first)


class SectionBuilder:
    """Collects headings and paragraphs, in reading order, into SectionDrafts.

    Used by formats whose headings have explicit levels (HTML <h1>-<h6>, Markdown #,
    underlined text headings). The heading path is a stack: a new heading closes every open
    heading at the same or a deeper level, so <h3> then <h2> gives two siblings, not a child.
    """

    def __init__(self) -> None:
        self._drafts: list[SectionDraft] = []
        self._stack: list[tuple[int, str]] = []  # (level, heading text)
        self._current = SectionDraft(heading=None, heading_path=[])

    def heading(self, level: int, text: str) -> None:
        if not text:
            return
        self._drafts.append(self._current)
        while self._stack and self._stack[-1][0] >= level:
            self._stack.pop()
        self._stack.append((level, text))
        self._current = SectionDraft(heading=text, heading_path=[t for _, t in self._stack])

    def paragraph(self, text: str, is_table: bool = False) -> None:
        if not text:
            return
        if is_table:
            self._current.table_indices.add(len(self._current.paragraphs))
        self._current.paragraphs.append(text)

    def finish(self) -> list[SectionDraft]:
        return [*self._drafts, self._current]


def first_heading(drafts: list[SectionDraft]) -> str | None:
    return next((d.heading_path[0] for d in drafts if d.heading_path), None)


def assemble_document(
    title: str | None, drafts: list[SectionDraft], page_count: int | None = None
) -> ParsedDocument:
    """Join section drafts into one document text and record each section's offsets.

    Sections with no body text (e.g. a title immediately followed by a sub-heading) are
    skipped as separate sections; their heading still appears in their children's paths.
    """
    text = ""
    sections: list[Section] = []
    for draft in drafts:
        paragraphs = [(p, i in draft.table_indices) for i, p in enumerate(draft.paragraphs) if p]
        if not paragraphs:
            continue

        # Build the section text piece by piece, remembering where each table lands.
        section_text = draft.heading or ""
        table_spans: list[tuple[int, int]] = []
        for paragraph, is_table in paragraphs:
            if section_text:
                section_text += PARAGRAPH_SEPARATOR
            if is_table:
                table_spans.append((len(section_text), len(section_text) + len(paragraph)))
            section_text += paragraph

        if text:
            text += SECTION_SEPARATOR
        start = len(text)
        text += section_text
        sections.append(
            Section(
                heading_path=draft.heading_path,
                text=section_text,
                char_start=start,
                char_end=len(text),
                page_start=draft.page_start,
                page_end=draft.page_end,
                table_spans=table_spans,
            )
        )

    if not sections:
        raise ParseError("No extractable text found")
    return ParsedDocument(title=title, text=text, sections=sections, page_count=page_count)
