from pathlib import Path

import pytest

from app.ingestion.chunking import chunk_document, split_section
from app.ingestion.parsing import parse
from app.ingestion.parsing.base import SectionDraft, assemble_document
from app.ingestion.parsing.pdf import parse_pdf
from app.ingestion.tokens import count_tokens
from app.ingestion.upload import detect_source_type

DEMO_DIR = Path(__file__).resolve().parents[2] / "data" / "demo_docs"
DEMO_PDF = DEMO_DIR / "billing-and-refunds-policy.pdf"

SENTENCES = [f"Sentence number {i} explains one small policy detail clearly." for i in range(40)]


def make_doc(*sections: tuple[list[str], list[str]]):
    """Build a ParsedDocument from (heading_path, paragraphs) pairs."""
    drafts = [
        SectionDraft(heading=path[-1] if path else None, heading_path=path, paragraphs=paras)
        for path, paras in sections
    ]
    return assemble_document("Test", drafts)


def test_small_sections_become_one_chunk_each():
    doc = parse_pdf(DEMO_PDF.read_bytes())
    chunks = chunk_document(doc)

    assert len(chunks) == len(doc.sections)
    for chunk, section in zip(chunks, doc.sections, strict=True):
        assert chunk.content == section.text
        assert chunk.heading_path == section.heading_path


def test_offsets_point_into_document_text():
    doc = make_doc((["A"], [" ".join(SENTENCES)]), (["B"], ["Short section."]))

    for chunk in chunk_document(doc, max_tokens=40, overlap_tokens=10):
        assert doc.text[chunk.char_start : chunk.char_end] == chunk.content


def test_long_section_is_split_within_limit_and_covers_everything():
    text = " ".join(SENTENCES)
    spans = split_section(text, max_tokens=40, overlap_tokens=10)

    assert len(spans) > 1
    assert all(count_tokens(text[s:e]) <= 40 for s, e in spans)
    assert spans[0][0] == 0 and spans[-1][1] == len(text)  # nothing lost at the ends
    for (_, prev_end), (next_start, _) in zip(spans, spans[1:], strict=False):
        # No text is lost between chunks: at most the whitespace between two sentences.
        assert text[prev_end:next_start].strip() == ""


def test_consecutive_chunks_overlap():
    text = " ".join(SENTENCES)
    spans = split_section(text, max_tokens=40, overlap_tokens=15)

    for (_, prev_end), (next_start, _) in zip(spans, spans[1:], strict=False):
        assert next_start < prev_end  # the next chunk starts inside the previous one


def test_zero_overlap_means_no_shared_text():
    text = " ".join(SENTENCES)
    spans = split_section(text, max_tokens=40, overlap_tokens=0)

    for (_, prev_end), (next_start, _) in zip(spans, spans[1:], strict=False):
        assert next_start >= prev_end


def test_chunks_split_at_sentence_boundaries():
    text = " ".join(SENTENCES)
    for start, end in split_section(text, max_tokens=40, overlap_tokens=10):
        assert text[start:end].startswith("Sentence number")
        assert text[start:end].endswith("clearly.")


def test_chunks_never_cross_sections():
    doc = make_doc((["A"], [" ".join(SENTENCES)]), (["B"], [" ".join(SENTENCES)]))
    chunks = chunk_document(doc, max_tokens=40, overlap_tokens=10)

    for chunk in chunks:
        section = next(s for s in doc.sections if s.heading_path == chunk.heading_path)
        assert section.char_start <= chunk.char_start and chunk.char_end <= section.char_end
    assert {tuple(c.heading_path) for c in chunks} == {("A",), ("B",)}


def test_giant_sentence_is_split_by_words():
    giant = " ".join(["word"] * 200) + "."
    spans = split_section(giant, max_tokens=30, overlap_tokens=5)

    assert len(spans) > 1
    assert all(count_tokens(giant[s:e]) <= 30 for s, e in spans)


def test_invalid_overlap_is_rejected():
    doc = make_doc((["A"], ["Text."]))
    with pytest.raises(ValueError, match="overlap"):
        chunk_document(doc, max_tokens=50, overlap_tokens=50)


# --- Tables ------------------------------------------------------------------------------

TABLE_ROWS = [
    f"Plan: Plan {i} | Seats: {i * 10} | Support: Email within {i} days" for i in range(30)
]


def make_table_doc():
    drafts = [
        SectionDraft(
            heading="Plans",
            heading_path=["Plans"],
            paragraphs=["Intro sentence about plans.", "\n".join(TABLE_ROWS), "Closing note."],
            table_indices={1},
        )
    ]
    return assemble_document("Test", drafts)


def test_large_table_is_split_between_rows_never_inside_a_row():
    doc = make_table_doc()
    chunks = chunk_document(doc, max_tokens=60, overlap_tokens=15)

    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.token_count <= 60
        for line in chunk.content.splitlines():
            if line.startswith("Plan:"):
                assert line in TABLE_ROWS  # every table line in a chunk is a complete row


def test_every_table_row_appears_in_some_chunk():
    doc = make_table_doc()
    chunks = chunk_document(doc, max_tokens=60, overlap_tokens=15)

    all_lines = {line for chunk in chunks for line in chunk.content.splitlines()}
    assert set(TABLE_ROWS) <= all_lines


def test_contains_table_flag():
    doc = make_table_doc()
    chunks = chunk_document(doc, max_tokens=60, overlap_tokens=0)

    assert chunks[0].contains_table  # intro + first rows
    assert any(c.contains_table for c in chunks)
    assert not chunk_document(make_doc((["A"], ["No tables here."])))[0].contains_table


def test_table_offsets_point_into_document_text():
    doc = make_table_doc()
    for chunk in chunk_document(doc, max_tokens=60, overlap_tokens=15):
        assert doc.text[chunk.char_start : chunk.char_end] == chunk.content


# --- Every demo document, every format ------------------------------------------------------


@pytest.mark.parametrize("path", sorted(DEMO_DIR.iterdir()), ids=lambda p: p.name)
@pytest.mark.parametrize("max_tokens,overlap", [(300, 50), (60, 15)])
def test_every_demo_doc_chunks_cleanly(path, max_tokens, overlap):
    doc = parse(detect_source_type(path.name), path.read_bytes())
    chunks = chunk_document(doc, max_tokens=max_tokens, overlap_tokens=overlap)

    assert chunks
    for chunk in chunks:
        assert doc.text[chunk.char_start : chunk.char_end] == chunk.content
        assert chunk.token_count <= max_tokens
        assert chunk.heading_path == next(
            s.heading_path
            for s in doc.sections
            if s.char_start <= chunk.char_start and chunk.char_end <= s.char_end
        )
