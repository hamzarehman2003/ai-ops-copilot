"""HTML parser: headings, paragraphs, lists, and tables from web pages and help articles.

Unlike a PDF, HTML already says what is a heading, a paragraph, or a table, so nothing is
guessed from fonts. The work is mostly deciding what *not* to read:

1. Drop what is never content: <script>, <style>, <nav>, <aside>, forms and buttons, the
   page-level <header>/<footer> (site chrome around the article), and hidden elements.
   Hidden text is dropped on purpose: readers never see it, so it is a classic place to
   hide prompt-injection text.
2. Read only the main content: <main>, else <article>, else <body>.
3. Walk the elements in document order: <h1>-<h6> start a section (level = the number),
   block elements (<p>, <li>, <pre>, ...) become paragraphs, <table> becomes one line per
   row via render_table. Inline tags (<strong>, <code>, <a>) only contribute their text.

The Markdown parser renders Markdown to HTML and reuses `parse_html_string`.

Out of scope for now: colspan/rowspan (cells may shift columns), text inside <iframe>s, and
pages that build their content with JavaScript (we only see the HTML that was uploaded).
"""

import re

from bs4 import BeautifulSoup, NavigableString, Tag
from bs4.element import PreformattedString

from app.ingestion.parsing.base import (
    ParsedDocument,
    SectionBuilder,
    assemble_document,
    decode_text,
    first_heading,
    normalize_line,
    render_table,
)

ALWAYS_DROP = [
    "script", "style", "noscript", "template", "nav", "aside",
    "form", "button", "input", "select", "textarea", "iframe", "svg", "canvas",
]  # fmt: skip
PAGE_CHROME = ["header", "footer"]  # dropped unless inside <main>/<article>
CONTENT_ROOTS = ["main", "article"]
HEADING_LEVELS = {f"h{n}": n for n in range(1, 7)}
BLOCK_TAGS = {
    "p", "div", "section", "article", "main", "header", "footer", "ul", "ol", "li",
    "dl", "dt", "dd", "blockquote", "figure", "figcaption", "details", "summary",
    "address", "hr",
}  # fmt: skip
LINE_BREAK = chr(0)  # placeholder for <br>: survives whitespace normalization, then -> newline
HIDDEN_STYLE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.IGNORECASE)


def parse_html(data: bytes) -> ParsedDocument:
    return parse_html_string(decode_text(data))


def parse_html_string(markup: str) -> ParsedDocument:
    soup = BeautifulSoup(markup, "html.parser")
    _drop_non_content(soup)
    root = soup.find(CONTENT_ROOTS[0]) or soup.find(CONTENT_ROOTS[1]) or soup.body or soup

    builder = SectionBuilder()
    walker = _Walker(builder)
    walker.walk(root)
    walker.flush()

    drafts = builder.finish()
    return assemble_document(_pick_title(soup) or first_heading(drafts), drafts)


def _drop_non_content(soup: BeautifulSoup) -> None:
    for tag in soup.find_all(ALWAYS_DROP):
        if not tag.decomposed:  # may already be gone with a dropped parent
            tag.decompose()
    for tag in soup.find_all(PAGE_CHROME):
        if not tag.decomposed and tag.find_parent(CONTENT_ROOTS) is None:
            tag.decompose()
    for tag in soup.find_all(_is_hidden):
        if not tag.decomposed:
            tag.decompose()


def _is_hidden(tag: Tag) -> bool:
    return (
        tag.has_attr("hidden")
        or tag.get("aria-hidden") == "true"
        or bool(HIDDEN_STYLE.search(tag.get("style") or ""))
    )


def _pick_title(soup: BeautifulSoup) -> str | None:
    """The first <h1> (clean), else <title> (often has a " | Site name" suffix)."""
    for tag in (soup.find("h1"), soup.title):
        if tag is not None and (text := normalize_line(tag.get_text(" "))):
            return text
    return None


class _Walker:
    """Walks the element tree, collecting inline text until a block boundary."""

    def __init__(self, builder: SectionBuilder) -> None:
        self.builder = builder
        self.buffer: list[str] = []  # inline text of the paragraph being read
        self.marker = ""  # list marker ("- " or "3. ") for the next paragraph

    def walk(self, node: Tag) -> None:
        for child in node.children:
            if isinstance(child, PreformattedString):  # comments, doctype, CDATA
                continue
            if isinstance(child, NavigableString):
                self.buffer.append(str(child))
                continue
            if not isinstance(child, Tag):
                continue

            name = child.name
            if name in HEADING_LEVELS:
                self.flush()
                self.builder.heading(HEADING_LEVELS[name], normalize_line(child.get_text(" ")))
            elif name == "table":
                self.flush()
                self._table(child)
            elif name == "pre":
                self.flush()
                self.builder.paragraph(_preformatted(child.get_text()))
            elif name == "br":
                self.buffer.append(LINE_BREAK)
            elif name in BLOCK_TAGS:
                self.flush()
                if name == "li":
                    self.marker = _list_marker(child)
                self.walk(child)
                self.flush()
            else:  # inline: <strong>, <code>, <a>, <span>, ...
                self.walk(child)

    def flush(self) -> None:
        # Newlines in HTML source are just wrapping; only <br> is a real line break.
        lines = (normalize_line(part) for part in "".join(self.buffer).split(LINE_BREAK))
        text = "\n".join(line for line in lines if line)
        self.buffer.clear()
        if text:
            self.builder.paragraph(self.marker + text)
            self.marker = ""

    def _table(self, table: Tag) -> None:
        caption = table.find("caption")
        if caption is not None and caption.find_parent("table") is table:
            self.builder.paragraph(normalize_line(caption.get_text(" ")))
        # Only this table's rows, not the rows of a table nested inside a cell.
        rows = [tr for tr in table.find_all("tr") if tr.find_parent("table") is table]
        cells = [tr.find_all(["th", "td"], recursive=False) for tr in rows]
        # <th> cells in the first row = a real header row; otherwise let render_table guess.
        header = True if cells and cells[0] and all(c.name == "th" for c in cells[0]) else None
        text = render_table([[c.get_text(" ") for c in row] for row in cells], header=header)
        self.builder.paragraph(text, is_table=True)


def _list_marker(li: Tag) -> str:
    """Keep list numbering: step order matters in instructions ("1. ... 2. ...")."""
    parent = li.parent
    if parent is not None and parent.name == "ol":
        try:
            start = int(parent.get("start") or 1)
        except ValueError:
            start = 1
        return f"{start + len(li.find_previous_siblings('li'))}. "
    return "- "


def _preformatted(text: str) -> str:
    """Code blocks keep their line breaks (each line normalized, blank lines dropped)."""
    return "\n".join(line for line in map(normalize_line, text.splitlines()) if line)
