"""Upload the demo documents through the API and wait until they are indexed.

- data/demo_docs/*  -> tasklane-support (as admin@tasklane.example)
- data/acme_docs/*  -> acme-demo        (as admin@acme.example), for tenant-isolation tests

Usage:
    inside Docker:   docker compose exec api python -m scripts.upload_demo_docs
    from the host:   python -m scripts.upload_demo_docs --api-url http://localhost:8001
"""

import argparse
import sys
import time
from pathlib import Path

import httpx

# backend/scripts/ -> repo root locally; /app/scripts/ -> / in Docker (data is mounted at /data)
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
UPLOADS = [("demo_docs", "admin@tasklane.example"), ("acme_docs", "admin@acme.example")]


def upload_dir(client: httpx.Client, docs_dir: Path, user: str) -> tuple[list[str], int]:
    pending, failures = [], 0
    for path in sorted(p for p in docs_dir.iterdir() if p.is_file()):
        response = client.post(
            "/api/sources",
            headers={"X-User": user},
            files={"file": (path.name, path.read_bytes())},
        )
        if response.is_success:
            body = response.json()
            outcome = "duplicate" if body["duplicate"] else "created"
            print(f"{outcome:<9} v{body['version']['version_number']}  {path.name}  ({user})")
            if body["duplicate"] and body["version"]["status"] in ("pending", "failed"):
                # Uploaded earlier but never indexed (e.g. before the pipeline existed).
                client.post(f"/api/sources/{body['document_id']}/reindex", headers={"X-User": user})
            pending.append(body["document_id"])
        else:
            failures += 1
            print(f"FAILED {response.status_code}  {path.name}: {response.text}")
    return pending, failures


def wait_until_indexed(client: httpx.Client, user: str, ids: list[str], timeout: float) -> int:
    deadline = time.monotonic() + timeout
    remaining = set(ids)
    failed = 0
    while remaining and time.monotonic() < deadline:
        for doc_id in list(remaining):
            body = client.get(f"/api/sources/{doc_id}", headers={"X-User": user}).json()
            status = body["latest_version"]["status"]
            if status in ("ready", "failed"):
                remaining.discard(doc_id)
                failed += status == "failed"
                print(f"{status:<9} {body['filename']}")
        time.sleep(1)
    return failed + len(remaining)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--timeout", type=float, default=600, help="seconds to wait for indexing")
    args = parser.parse_args()

    problems = 0
    with httpx.Client(base_url=args.api_url, timeout=60) as client:
        for folder, user in UPLOADS:
            ids, failures = upload_dir(client, args.data_dir / folder, user)
            problems += failures + wait_until_indexed(client, user, ids, args.timeout)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
