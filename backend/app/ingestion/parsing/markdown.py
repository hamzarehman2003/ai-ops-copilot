"""Markdown parser: render to HTML, then reuse the HTML parser.

Markdown is a shorthand for HTML (`#` = <h1>, `- ` = <li>, `| a | b |` = <table>), so a real
Markdown parser (markdown-it-py, CommonMark + tables) turns it into HTML and the HTML parser
does the rest. One structure walker and one table renderer for both formats, and inline
syntax (`**bold**`, `` `code` ``, links) disappears for free instead of ending up in chunks.

Hand-written regexes on `#` lines are the usual alternative, but they break on `#` inside
code blocks, setext headings (underlined with ===), and tables.
"""

import re

from markdown_it import MarkdownIt

from app.ingestion.parsing.base import ParsedDocument, decode_text
from app.ingestion.parsing.html import parse_html_string

# YAML front matter (--- ... --- at the very top): metadata for static-site tools, not text.
FRONT_MATTER = re.compile(r"\A---[ \t]*\n.*?\n---[ \t]*\n", re.DOTALL)

_markdown = MarkdownIt("commonmark").enable(["table", "strikethrough"])


def parse_markdown(data: bytes) -> ParsedDocument:
    text = FRONT_MATTER.sub("", decode_text(data), count=1)
    return parse_html_string(_markdown.render(text))
