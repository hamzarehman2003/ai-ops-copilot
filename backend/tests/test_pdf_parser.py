import io
from pathlib import Path

import pymupdf
import pytest

from app.ingestion.parsing import PARSERS, ParseError, parse
from app.ingestion.parsing.pdf import _join_lines, parse_pdf
from app.models import SourceType

DEMO_PDF = (
    Path(__file__).resolve().parents[2] / "data" / "demo_docs" / "billing-and-refunds-policy.pdf"
)

BODY = "This is ordinary body text that is long enough to set the body font size. " * 3


TABLE_CSS = "table { border-collapse: collapse; } th, td { border: 1px solid #999; padding: 3pt; }"


def make_pdf(html: str, css: str = "") -> bytes:
    """Render HTML to a PDF (same technique as scripts/build_demo_pdf.py)."""
    story = pymupdf.Story(html=html, user_css=css)
    out = io.BytesIO()
    writer = pymupdf.DocumentWriter(out)
    mediabox = pymupdf.paper_rect("a4")
    more = True
    while more:
        device = writer.begin_page(mediabox)
        more, _ = story.place(mediabox + (56, 64, -56, -64))
        story.draw(device)
        writer.end_page()
    writer.close()
    return out.getvalue()


@pytest.fixture(scope="module")
def demo():
    return parse_pdf(DEMO_PDF.read_bytes())


# --- The demo billing policy ---------------------------------------------------------------


def test_demo_title_and_sections(demo):
    assert demo.title == "Tasklane Billing and Refund Policy"  # from PDF metadata
    assert demo.page_count == 2
    assert [s.heading_path[-1] for s in demo.sections[1:]] == [
        "1. Scope",
        "2. Billing cycles",
        "3. Failed payments",
        "4. Refund eligibility",
        "5. Exceptions",
        "6. Taxes",
        "7. Changing the payment method",
        "8. Chargebacks",
        "9. Contact",
    ]


def test_demo_heading_paths_are_hierarchical(demo):
    refunds = next(s for s in demo.sections if s.heading_path[-1] == "4. Refund eligibility")
    assert refunds.heading_path == ["Billing and Refund Policy", "4. Refund eligibility"]
    assert "14 days from purchase" in refunds.text


def test_demo_running_header_and_page_numbers_removed(demo):
    assert "Page 1 of 2" not in demo.text
    assert "Page 2 of 2" not in demo.text
    assert "Internal & Customer-facing" not in demo.text


def test_demo_section_spanning_page_break(demo):
    exceptions = next(s for s in demo.sections if s.heading_path[-1] == "5. Exceptions")
    assert (exceptions.page_start, exceptions.page_end) == (1, 2)
    assert "Duplicate charges caused by a Tasklane billing error" in exceptions.text


def test_demo_bold_table_header_cells_are_not_headings(demo):
    headings = {h for s in demo.sections for h in s.heading_path}
    assert "Plan and billing" not in headings
    assert "Refund window" not in headings


def test_demo_table_rows_keep_their_columns(demo):
    refunds = next(s for s in demo.sections if s.heading_path[-1] == "4. Refund eligibility")

    # The row that used to come out scrambled ("Full refund" before "Pro, annual"):
    assert (
        "Plan and billing: Pro, annual | Refund window: 14 days from purchase or renewal"
        " | Refund type: Full refund"
    ) in refunds.text
    assert (
        "Plan and billing: Pro, annual (after 14 days) | Refund window: Not eligible"
        " | Refund type: Remaining term stays active"
    ) in refunds.text
    # The raw cell lines are gone: no header line, no orphan cells.
    assert "Plan and billing Refund window Refund type" not in refunds.text
    assert "\n\nFull refund\n\n" not in refunds.text


def test_demo_table_span_and_surrounding_text(demo):
    refunds = next(s for s in demo.sections if s.heading_path[-1] == "4. Refund eligibility")

    assert len(refunds.table_spans) == 1
    start, end = refunds.table_spans[0]
    table = refunds.text[start:end]
    assert table.startswith("Plan and billing: Pro, monthly")
    assert table.endswith("Refund type: Account credit only")
    assert len(table.splitlines()) == 5  # 5 data rows; the header row became column names
    # The paragraph after the table is still in the section, after the table.
    assert refunds.text.index("Refunds are issued to the original payment method") > end


def test_bordered_table_in_generated_pdf():
    pdf = make_pdf(
        f"<h1>Plans</h1><p>{BODY}</p>"
        "<table><tr><th>Plan</th><th>Seats</th></tr>"
        "<tr><td>Free</td><td>5</td></tr><tr><td>Pro</td><td>500</td></tr></table>"
        f"<p>{BODY}</p>",
        css=TABLE_CSS,
    )
    section = parse_pdf(pdf).sections[0]

    assert len(section.table_spans) == 1
    start, end = section.table_spans[0]
    assert section.text[start:end] == "Plan: Free | Seats: 5\nPlan: Pro | Seats: 500"


def test_demo_ligatures_normalized(demo):
    assert "ﬁ" not in demo.text  # 'ﬁ' ligature
    assert "on file" in demo.text


def test_demo_offsets_match_text(demo):
    for section in demo.sections:
        assert demo.text[section.char_start : section.char_end] == section.text


# --- Generated PDFs: specific behaviours ----------------------------------------------------


def test_heading_path_resets_at_same_or_higher_level():
    pdf = make_pdf(
        f"<h1>Guide A</h1><h2>Setup</h2><p>{BODY}</p><h1>Guide B</h1><h2>Usage</h2><p>{BODY}</p>"
    )
    doc = parse_pdf(pdf)

    assert [s.heading_path for s in doc.sections] == [["Guide A", "Setup"], ["Guide B", "Usage"]]


def test_title_falls_back_to_first_top_heading_without_metadata():
    doc = parse_pdf(make_pdf(f"<h1>Onboarding Handbook</h1><h2>Day one</h2><p>{BODY}</p>"))

    assert doc.title == "Onboarding Handbook"


def test_bold_line_at_body_size_is_a_heading():
    doc = parse_pdf(make_pdf(f"<p>{BODY}</p><p><b>Overview</b></p><p>{BODY}</p>"))

    assert [s.heading_path for s in doc.sections] == [[], ["Overview"]]


def test_bold_sentence_is_not_a_heading():
    doc = parse_pdf(make_pdf(f"<p>{BODY}</p><p><b>Do not share passwords.</b></p><p>{BODY}</p>"))

    assert all(s.heading_path == [] for s in doc.sections)


def test_document_without_headings_is_one_section():
    doc = parse_pdf(make_pdf(f"<p>{BODY}</p><p>{BODY}</p>"))

    assert len(doc.sections) == 1
    assert doc.sections[0].heading_path == []
    assert doc.title is None


def test_page_without_text_layer_is_rejected():
    blank = pymupdf.open()
    blank.new_page()
    with pytest.raises(ParseError, match="no text layer"):
        parse_pdf(blank.tobytes())


def test_corrupt_pdf_is_rejected():
    with pytest.raises(ParseError, match="Could not open PDF"):
        parse_pdf(b"%PDF-1.7 this is not really a pdf")


def test_encrypted_pdf_is_rejected():
    doc = pymupdf.open(stream=make_pdf(f"<p>{BODY}</p>"), filetype="pdf")
    encrypted = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="u", owner_pw="o")
    with pytest.raises(ParseError, match="password"):
        parse_pdf(encrypted)


def test_join_lines_undoes_hyphenation():
    assert _join_lines(["The pay-", "ment failed"]) == "The payment failed"
    assert _join_lines(["payment-", "Update link"]) == "payment- Update link"
    assert _join_lines(["one", "two"]) == "one two"


def test_parse_dispatches_by_type_and_every_type_has_a_parser():
    assert parse(SourceType.PDF, DEMO_PDF.read_bytes()).sections
    assert set(PARSERS) == set(SourceType)
    with pytest.raises(ParseError, match="No extractable text"):
        parse(SourceType.MARKDOWN, b"# Title")  # a heading with no body is not content
