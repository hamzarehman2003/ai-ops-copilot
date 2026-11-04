"""Split a parsed document into chunks: the units that get embedded and retrieved.

Rules:
1. A chunk never crosses a section boundary, so every chunk has exactly one heading path.
2. A section that fits in `max_tokens` becomes one chunk (tables included).
3. A longer section is split into pieces and packed into chunks:
   - in normal text, a piece is a sentence (or a word, for a giant sentence);
   - in a table, a piece is a whole row, so a row is never cut in half. Each row already
     repeats its column names (see `render_table`), so it still makes sense on its own.
4. Consecutive chunks of the same section share about `overlap_tokens` of text, so a fact
   that sits on a boundary still appears whole in at least one chunk.

Every chunk keeps offsets into the document text: doc.text[char_start:char_end] == content.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from app.ingestion.parsing.base import ParsedDocument, Section
from app.ingestion.tokens import count_tokens

DEFAULT_MAX_TOKENS = 300
DEFAULT_OVERLAP_TOKENS = 50

# A sentence ends at . ! or ? followed by whitespace; a blank line also ends a piece.
SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+|\n\s*\n")
ROW_BOUNDARY = re.compile(r"\n")  # tables are rendered one row per line
WORD = re.compile(r"\S+")

Span = tuple[int, int]  # (start, end) character positions inside a section's text


@dataclass
class ChunkDraft:
    content: str
    heading_path: list[str]
    char_start: int  # offsets into ParsedDocument.text
    char_end: int
    page_start: int | None  # page range of the whole section (finer detail is not tracked)
    page_end: int | None
    token_count: int
    contains_table: bool = False


def chunk_document(
    doc: ParsedDocument,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[ChunkDraft]:
    if not 0 <= overlap_tokens < max_tokens:
        raise ValueError("overlap_tokens must be >= 0 and smaller than max_tokens")

    chunks: list[ChunkDraft] = []
    for section in doc.sections:
        spans = split_section(section.text, max_tokens, overlap_tokens, section.table_spans)
        for start, end in spans:
            chunks.append(_make_chunk(section, start, end))
    return chunks


def split_section(
    text: str, max_tokens: int, overlap_tokens: int, table_spans: Sequence[Span] = ()
) -> list[Span]:
    """Return the (start, end) spans of the chunks for one section's text."""
    if count_tokens(text) <= max_tokens:
        return [(0, len(text))]

    pieces = _pieces(text, max_tokens, table_spans)
    windows: list[Span] = []
    i = 0
    while i < len(pieces):
        # Grow the window piece by piece while it still fits.
        j = i + 1  # a window always takes at least one piece
        while j < len(pieces) and count_tokens(text[pieces[i][0] : pieces[j][1]]) <= max_tokens:
            j += 1
        windows.append((pieces[i][0], pieces[j - 1][1]))

        if j == len(pieces):
            break
        # Start the next window a few pieces back, to create the overlap,
        # but always move forward by at least one piece.
        next_start = j
        while (
            next_start - 1 > i
            and count_tokens(text[pieces[next_start - 1][0] : pieces[j - 1][1]]) <= overlap_tokens
        ):
            next_start -= 1
        i = next_start
    return windows


def _pieces(text: str, max_tokens: int, table_spans: Sequence[Span]) -> list[Span]:
    """The units chunks are built from: sentences in normal text, whole rows in tables."""
    spans: list[Span] = []
    position = 0
    for table_start, table_end in sorted(table_spans):
        spans += _split_on(SENTENCE_BOUNDARY, text, position, table_start)  # text before table
        spans += _split_on(ROW_BOUNDARY, text, table_start, table_end)  # table rows
        position = table_end
    spans += _split_on(SENTENCE_BOUNDARY, text, position, len(text))  # text after last table

    # A single piece that is too big on its own (giant sentence or row) is split into words.
    pieces: list[Span] = []
    for start, end in spans:
        if count_tokens(text[start:end]) <= max_tokens:
            pieces.append((start, end))
        else:
            pieces.extend(
                (start + m.start(), start + m.end()) for m in WORD.finditer(text[start:end])
            )
    return pieces


def _split_on(boundary: re.Pattern, text: str, start: int, end: int) -> list[Span]:
    """Spans of text[start:end] between boundary matches, ignoring whitespace-only spans."""
    spans: list[Span] = []
    piece_start = start
    for match in boundary.finditer(text, start, end):
        if text[piece_start : match.start()].strip():
            spans.append((piece_start, match.start()))
        piece_start = match.end()
    if text[piece_start:end].strip():
        spans.append((piece_start, end))
    return spans


def _make_chunk(section: Section, start: int, end: int) -> ChunkDraft:
    content = section.text[start:end]
    return ChunkDraft(
        content=content,
        heading_path=section.heading_path,
        char_start=section.char_start + start,
        char_end=section.char_start + end,
        page_start=section.page_start,
        page_end=section.page_end,
        token_count=count_tokens(content),
        contains_table=any(
            t_start < end and start < t_end for t_start, t_end in section.table_spans
        ),
    )
