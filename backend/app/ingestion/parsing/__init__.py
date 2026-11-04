"""Turn uploaded file bytes into a `ParsedDocument`: one parser per format, same output."""

from collections.abc import Callable

from app.ingestion.parsing.base import ParsedDocument, ParseError, Section
from app.ingestion.parsing.html import parse_html
from app.ingestion.parsing.markdown import parse_markdown
from app.ingestion.parsing.pdf import parse_pdf
from app.ingestion.parsing.text import parse_text
from app.models import SourceType

PARSERS: dict[SourceType, Callable[[bytes], ParsedDocument]] = {
    SourceType.PDF: parse_pdf,
    SourceType.MARKDOWN: parse_markdown,
    SourceType.HTML: parse_html,
    SourceType.TEXT: parse_text,
}


def parse(source_type: SourceType, data: bytes) -> ParsedDocument:
    parser = PARSERS.get(source_type)
    if parser is None:
        raise ParseError(f"No parser for {source_type.value} files yet")
    return parser(data)


__all__ = ["PARSERS", "ParseError", "ParsedDocument", "Section", "parse"]
