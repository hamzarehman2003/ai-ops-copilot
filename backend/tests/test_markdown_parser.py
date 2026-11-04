from pathlib import Path

from app.ingestion.parsing import parse
from app.ingestion.parsing.markdown import parse_markdown
from app.models import SourceType

DEMO_DIR = Path(__file__).resolve().parents[2] / "data" / "demo_docs"


def test_demo_pricing_structure_and_table():
    doc = parse_markdown((DEMO_DIR / "pricing-and-plans.md").read_bytes())

    assert doc.title == "Tasklane Plans and Pricing"
    paths = [s.heading_path for s in doc.sections]
    assert ["Tasklane Plans and Pricing", "Feature availability notes", "Single sign-on"] in paths

    table_section = next(s for s in doc.sections if s.heading_path[-1] == "Plan comparison")
    assert (
        "Feature: Single sign-on (SAML SSO) | Free: No | Pro: No | Enterprise: Yes"
        in table_section.text.splitlines()
    )
    assert len(table_section.table_spans) == 1
    for s in doc.sections:
        assert doc.text[s.char_start : s.char_end] == s.text


def test_inline_syntax_is_removed():
    doc = parse_markdown(b"# Title\n\nUse **bold**, `code`, and [a link](https://x.example).\n")
    assert doc.sections[0].text == "Title\n\nUse bold, code, and a link."


def test_hash_inside_code_block_is_not_a_heading():
    doc = parse_markdown(b"# Real\n\n```\n# not a heading\nrun()\n```\n")
    assert [s.heading_path for s in doc.sections] == [["Real"]]
    assert "# not a heading\nrun()" in doc.text


def test_setext_heading_and_lists():
    doc = parse_markdown(b"Guide\n=====\n\nIntro.\n\n1. First\n2. Second\n\n- dot\n")
    assert doc.title == "Guide"
    assert doc.sections[0].text == "Guide\n\nIntro.\n\n1. First\n\n2. Second\n\n- dot"


def test_front_matter_is_dropped():
    doc = parse_markdown(b"---\ntitle: x\ntags: [a]\n---\n# Doc\n\nBody.\n")
    assert doc.text == "Doc\n\nBody."


def test_raw_html_script_is_dropped():
    doc = parse_markdown(b"# Doc\n\nText.\n\n<script>alert(1)</script>\n")
    assert "alert" not in doc.text


def test_dispatch():
    assert parse(SourceType.MARKDOWN, b"Hello *world*.").text == "Hello world."
