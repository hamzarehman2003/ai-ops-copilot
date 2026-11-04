"""Print what the parser extracts from a file: title, sections, heading paths, pages.

Usage (from backend/):
    python -m scripts.parse_file ../data/demo_docs/billing-and-refunds-policy.pdf
    python -m scripts.parse_file <file> --full     # print every section's full text
    python -m scripts.parse_file <file> --raw      # print the ParsedDocument object itself
"""

import argparse
import sys
from pathlib import Path
from pprint import pprint

from app.ingestion.parsing import ParseError, parse
from app.ingestion.upload import UploadError, detect_source_type


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", type=Path)
    parser.add_argument("--full", action="store_true", help="print full section text")
    parser.add_argument("--raw", action="store_true", help="print the ParsedDocument object")
    args = parser.parse_args()

    try:
        doc = parse(detect_source_type(args.path.name), args.path.read_bytes())
    except (UploadError, ParseError) as exc:
        print(f"Cannot parse {args.path.name}: {exc}")
        return 1

    if args.raw:
        # The exact object parse() returns, field by field.
        pprint(doc, width=100, sort_dicts=False)
        return 0

    print(f"Title:    {doc.title}")
    print(f"Pages:    {doc.page_count}")
    print(f"Sections: {len(doc.sections)}   Characters: {len(doc.text)}\n")
    for i, section in enumerate(doc.sections):
        path = " > ".join(section.heading_path) or "(no heading)"
        pages = ""
        if section.page_start is not None:  # PDFs only
            pages = f"p{section.page_start}" + (
                f"-{section.page_end}" if section.page_end != section.page_start else ""
            )
            pages += ", "
        print(f"[{i}] {path}   ({pages}chars {section.char_start}-{section.char_end})")
        body = section.text if args.full else section.text.replace("\n", " ")[:110] + "..."
        print(f"    {body}\n")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
