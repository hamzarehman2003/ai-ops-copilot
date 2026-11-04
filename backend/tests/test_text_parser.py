from pathlib import Path

import pytest

from app.ingestion.parsing import ParseError, parse
from app.ingestion.parsing.text import parse_text
from app.models import SourceType

DEMO_DIR = Path(__file__).resolve().parents[2] / "data" / "demo_docs"
API_TITLE = "TASKLANE REST API — RATE LIMITS AND ERROR HANDLING"


def test_demo_rate_limits_headings():
    doc = parse_text((DEMO_DIR / "api-rate-limits.txt").read_bytes())

    assert doc.title == API_TITLE  # ALL-CAPS first line
    assert [s.heading_path for s in doc.sections] == [
        [API_TITLE],
        [API_TITLE, "OVERVIEW"],  # underlined with ----- -> level 2
        [API_TITLE, "LIMITS BY PLAN"],
        [API_TITLE, "RESPONSE HEADERS"],
        [API_TITLE, "WHEN THE LIMIT IS EXCEEDED"],
        [API_TITLE, "OTHER ERROR CODES"],
        [API_TITLE, "BEST PRACTICES"],
    ]
    assert "-----" not in doc.text  # underlines are not content
    for s in doc.sections:
        assert doc.text[s.char_start : s.char_end] == s.text


def test_demo_aligned_list_keeps_one_item_per_line():
    doc = parse_text((DEMO_DIR / "api-rate-limits.txt").read_bytes())
    limits = next(s for s in doc.sections if s.heading_path[-1] == "LIMITS BY PLAN")
    assert "Free 60 requests per minute\nPro 300 requests per minute\n" in limits.text


def test_demo_forum_export_has_no_headings():
    doc = parse_text((DEMO_DIR / "community-tips-export.txt").read_bytes())

    # Separator lines are dropped; the mixed-case title line is not a heading, and neither
    # is user-written text in a post (a heading would be repeated as context on chunks).
    assert len(doc.sections) == 1
    assert doc.sections[0].heading_path == []
    assert doc.title.startswith("TASKLANE COMMUNITY FORUM")
    assert "-----" not in doc.text


def test_underline_levels_and_separators():
    text = b"Guide\n=====\n\nIntro.\n\nPart\n----\n\nBody.\n\n*****\n\nMore body.\n"
    doc = parse_text(text)
    assert [s.heading_path for s in doc.sections] == [["Guide"], ["Guide", "Part"]]
    assert doc.sections[1].text == "Part\n\nBody.\n\nMore body."


def test_dashes_under_a_multi_line_paragraph_are_a_separator_not_a_heading():
    doc = parse_text(b"First line of a paragraph\nsecond line.\n-----\nNext.\n")
    assert doc.sections[0].heading_path == []
    assert doc.text == "First line of a paragraph\nsecond line.\n\nNext."


def test_caps_heading_needs_its_own_line_and_no_indentation():
    doc = parse_text(b"Intro text\nNOT A HEADING\n\n  ALSO NOT\n\nREAL HEADING\nBody.\n")
    assert [s.heading_path for s in doc.sections] == [[], ["REAL HEADING"]]


def test_crlf_bom_and_whitespace_are_normalized():
    doc = parse_text("﻿Title line\r\n\r\nSome   text\r\n".encode())
    assert doc.text == "Title line\n\nSome text"
    assert doc.title == "Title line"


def test_empty_and_invalid_files_are_rejected():
    with pytest.raises(ParseError, match="No extractable text"):
        parse_text(b"\n \n-----\n")
    with pytest.raises(ParseError, match="UTF-8"):
        parse_text(b"caf\xe9")


def test_dispatch():
    assert parse(SourceType.TEXT, b"Plain.").text == "Plain."
