from pathlib import Path

import pytest

from app.ingestion.parsing import ParseError, parse
from app.ingestion.parsing.html import parse_html
from app.models import SourceType

DEMO_DIR = Path(__file__).resolve().parents[2] / "data" / "demo_docs"


def html(body: str, head: str = "") -> bytes:
    return f"<!doctype html><html><head>{head}</head><body>{body}</body></html>".encode()


@pytest.fixture(scope="module")
def sso():
    return parse_html((DEMO_DIR / "sso-setup-guide.html").read_bytes())


# --- The demo SSO guide ----------------------------------------------------------------


def test_demo_title_and_sections(sso):
    assert sso.title == "Set up SAML single sign-on"  # <h1>, not the "| Help Center" <title>
    assert [s.heading_path for s in sso.sections[1:]] == [
        ["Set up SAML single sign-on", "Before you begin"],
        ["Set up SAML single sign-on", "Step 1: Create the Tasklane app in your IdP"],
        ["Set up SAML single sign-on", "Step 2: Connect the IdP in Tasklane"],
        ["Set up SAML single sign-on", "Step 3: Enforce SSO"],
        ["Set up SAML single sign-on", "Troubleshooting"],
    ]


def test_demo_boilerplate_removed(sso):
    for noise in ["analytics", "font-family", "System status", "Privacy", "Was this article"]:
        assert noise not in sso.text


def test_demo_lists_keep_order_and_inline_text(sso):
    step1 = sso.sections[2].text
    assert "1. In your IdP, create a new SAML 2.0 application" in step1
    # <strong>/<code> contribute their text without extra spaces; entities are decoded
    assert "2. Set the ACS URL to https://auth.tasklane.example/saml/acs/<workspace-id>." in step1
    assert "- You must be a workspace Owner." in sso.sections[1].text


def test_demo_table_rows(sso):
    section = sso.sections[-1]
    assert (
        "Error code: SSO-429 | Meaning: Too many sign-in attempts from the same user. | "
        "Fix: Wait 15 minutes and try again." in section.text.splitlines()
    )
    [(start, end)] = section.table_spans
    assert section.text[start:end].count("\n") == 4  # 5 rows, header row not repeated


def test_demo_offsets(sso):
    for s in sso.sections:
        assert sso.text[s.char_start : s.char_end] == s.text
        assert s.page_start is None


def test_page_header_and_footer_outside_main_are_dropped():
    doc = parse_html((DEMO_DIR / "integrations-faq.html").read_bytes())
    assert doc.title == "Integrations FAQ"
    assert "Help Center" not in doc.text and "©" not in doc.text


# --- Small HTML cases --------------------------------------------------------------------


def test_hidden_elements_are_dropped():
    doc = parse_html(
        html(
            "<h1>Doc</h1><p>Visible text.</p>"
            '<p style="display: none">Hidden instruction.</p>'
            "<div hidden>Also hidden.</div>"
            '<span aria-hidden="true">Icon label.</span>'
            "<!-- an HTML comment -->"
        )
    )
    assert doc.sections[0].text == "Doc\n\nVisible text."


def test_header_inside_article_is_kept():
    doc = parse_html(
        html("<header>Site menu</header><article><header><h1>Title</h1></header><p>Body.</p>")
    )
    assert doc.title == "Title"
    assert "Site menu" not in doc.text
    assert doc.sections[0].heading_path == ["Title"]


def test_heading_path_follows_levels():
    doc = parse_html(
        html("<h1>A</h1><p>a</p><h3>A.1.1</h3><p>x</p><h2>A.2</h2><p>y</p><h1>B</h1><p>b</p>")
    )
    assert [s.heading_path for s in doc.sections] == [
        ["A"],
        ["A", "A.1.1"],
        ["A", "A.2"],  # h2 closes the h3: sibling, not child
        ["B"],
    ]


def test_br_keeps_line_breaks_but_source_newlines_do_not():
    doc = parse_html(html("<p>Line one<br>Line two</p><p>wrapped\n   in source</p>"))
    assert doc.text == "Line one\nLine two\n\nwrapped in source"


def test_table_header_from_th_and_nested_table_rows_not_duplicated():
    doc = parse_html(
        html(
            "<table><caption>Limits</caption>"
            "<tr><th>Plan</th><th>Limit</th></tr>"
            "<tr><td>2024</td><td>100</td></tr>"
            "<tr><td>Pro</td><td><table><tr><td>inner</td></tr></table></td></tr>"
            "</table>"
        )
    )
    # Numeric first data row would fool the guess; <th> makes the header certain.
    assert doc.text == "Limits\n\nPlan: 2024 | Limit: 100\nPlan: Pro | Limit: inner"
    assert len(doc.sections[0].table_spans) == 1


def test_ordered_list_start_attribute():
    doc = parse_html(html('<ol start="4"><li>Four</li><li>Five</li></ol>'))
    assert doc.text == "4. Four\n\n5. Five"


def test_pre_keeps_lines():
    doc = parse_html(html("<pre>GET /v2/tasks\n\n  Authorization: Bearer x</pre>"))
    assert doc.text == "GET /v2/tasks\nAuthorization: Bearer x"


def test_title_falls_back_to_title_tag():
    doc = parse_html(html("<p>No headings here.</p>", head="<title>Page title</title>"))
    assert doc.title == "Page title"
    assert doc.sections[0].heading_path == []


def test_empty_page_and_invalid_utf8_are_rejected():
    with pytest.raises(ParseError, match="No extractable text"):
        parse_html(html("<nav>Only navigation</nav><script>x()</script>"))
    with pytest.raises(ParseError, match="UTF-8"):
        parse_html(b"<p>caf\xe9</p>")


def test_dispatch():
    assert parse(SourceType.HTML, html("<p>Hi.</p>")).text == "Hi."
