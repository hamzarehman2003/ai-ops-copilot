"""Parse a file and print its chunks.

Usage (from backend/):
    python -m scripts.chunk_file ../data/demo_docs/billing-and-refunds-policy.pdf
    python -m scripts.chunk_file <file> --max-tokens 60 --overlap 15   # force splitting
"""

import argparse
import sys
from pathlib import Path

from app.ingestion.chunking import DEFAULT_MAX_TOKENS, DEFAULT_OVERLAP_TOKENS, chunk_document
from app.ingestion.parsing import ParseError, parse
from app.ingestion.upload import UploadError, detect_source_type


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", type=Path)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--overlap", type=int, default=DEFAULT_OVERLAP_TOKENS)
    args = parser.parse_args()

    try:
        doc = parse(detect_source_type(args.path.name), args.path.read_bytes())
    except (UploadError, ParseError) as exc:
        print(f"Cannot parse {args.path.name}: {exc}")
        return 1

    chunks = chunk_document(doc, max_tokens=args.max_tokens, overlap_tokens=args.overlap)
    print(f"{len(doc.sections)} sections -> {len(chunks)} chunks ")
    print(f"(max {args.max_tokens} tokens, overlap {args.overlap})\n")
    for i, chunk in enumerate(chunks):
        heading = " > ".join(chunk.heading_path) or "(no heading)"
        page = f"  (p{chunk.page_start})" if chunk.page_start is not None else ""
        print(f"--- chunk {i}  [{chunk.token_count} tokens]  {heading}{page}")
        print(chunk.content + "\n")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
