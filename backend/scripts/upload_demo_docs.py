"""Upload every file in data/demo_docs/ through the API (exercises the real endpoint).

Usage:
    inside Docker:   docker compose exec api python -m scripts.upload_demo_docs
    from the host:   python -m scripts.upload_demo_docs --api-url http://localhost:8001
"""

import argparse
import sys
from pathlib import Path

import httpx

# backend/scripts/ -> repo root locally; /app/scripts/ -> / in Docker (data is mounted at /data)
DEFAULT_DOCS_DIR = Path(__file__).resolve().parents[2] / "data" / "demo_docs"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--workspace", default="tasklane-support")
    parser.add_argument("--docs-dir", type=Path, default=DEFAULT_DOCS_DIR)
    args = parser.parse_args()

    files = sorted(p for p in args.docs_dir.iterdir() if p.is_file())
    if not files:
        print(f"No files found in {args.docs_dir}")
        return 1

    failures = 0
    with httpx.Client(base_url=args.api_url, headers={"X-Workspace": args.workspace}) as client:
        for path in files:
            response = client.post("/api/sources", files={"file": (path.name, path.read_bytes())})
            if response.is_success:
                body = response.json()
                outcome = "duplicate" if body["duplicate"] else "created"
                print(f"{outcome:<9} v{body['version']['version_number']}  {path.name}")
            else:
                failures += 1
                print(f"FAILED {response.status_code}  {path.name}: {response.text}")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
