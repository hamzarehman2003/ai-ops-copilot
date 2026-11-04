"""Plain-text parser: no markup, so structure comes from common writing conventions.

- A line underlined with ===== (level 1) or ----- (level 2) is a heading.
- A short ALL-CAPS line at the start of a block is a heading (level 1).
- Lines made only of a repeated symbol (-----, =====, *****) are separators: they end the
  current paragraph and are dropped.
- Blank lines separate paragraphs. Line breaks inside a paragraph are kept (each line
  normalized), because plain-text files often use them for aligned lists:
      Pro          300 requests per minute
  Re-flowing wrapped prose into one line would be nicer to read but needs guessing.

A file with no headings becomes one untitled section, titled by its first line.
"""

import re

from app.ingestion.parsing.base import (
    ParsedDocument,
    SectionBuilder,
    assemble_document,
    decode_text,
    first_heading,
    normalize_line,
)

SEPARATOR = re.compile(r"^\s*([-=*_~#])\1{2,}\s*$")  # 3+ of the same symbol, nothing else
MAX_HEADING_CHARS = 80
UNDERLINE_LEVELS = {"=": 1, "-": 2}


def parse_text(data: bytes) -> ParsedDocument:
    lines = decode_text(data).split("\n")
    builder = SectionBuilder()
    block: list[str] = []  # lines of the paragraph being read

    def flush() -> None:
        builder.paragraph("\n".join(filter(None, map(normalize_line, block))))
        block.clear()

    for i, line in enumerate(lines):
        next_line = lines[i + 1] if i + 1 < len(lines) else ""
        if not line.strip():
            flush()
        elif SEPARATOR.match(line):
            # "OVERVIEW" alone on a line, then "--------" right below it -> heading.
            level = UNDERLINE_LEVELS.get(_underline_char(line) or "")
            if level and len(block) == 1 and _short(block[0]):
                builder.heading(level, normalize_line(block.pop()))
            else:
                flush()
        elif not block and _is_caps_heading(line) and not _underline_char(next_line):
            builder.heading(1, normalize_line(line))
        else:
            block.append(line)
    flush()

    drafts = builder.finish()
    return assemble_document(first_heading(drafts) or _first_line(lines), drafts)


def _underline_char(line: str) -> str | None:
    match = SEPARATOR.match(line)
    return match.group(1) if match and match.group(1) in UNDERLINE_LEVELS else None


def _short(line: str) -> bool:
    return 0 < len(line.strip()) <= MAX_HEADING_CHARS


def _is_caps_heading(line: str) -> bool:
    letters = [c for c in line if c.isalpha()]
    return (
        not line[:1].isspace()  # indented lines are list/table content
        and _short(line)
        and len(letters) >= 2
        and all(c.isupper() for c in letters)
    )


def _first_line(lines: list[str]) -> str | None:
    first = next((normalize_line(ln) for ln in lines if ln.strip()), "")
    return first if 0 < len(first) <= 120 else None
