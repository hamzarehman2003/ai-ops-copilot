"""Reset the demo to its starting state: clears conversations, actions, audit entries for
actions, CRM changes, deprecated flags, and documents uploaded during the demo. Keeps users and
the indexed demo documents (no re-indexing needed). See app/demo_reset.py.

Usage:
    inside Docker:   docker compose exec api python -m scripts.reset_demo --yes
    from backend/:   .venv/Scripts/python -m scripts.reset_demo --yes
"""

import argparse
import sys
from pathlib import Path

from app.config import get_settings
from app.db import SessionLocal
from app.demo_reset import demo_filenames, reset_demo

# backend/scripts/ -> repo root locally; /app/scripts/ -> / in Docker (data is mounted at /data)
DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--yes", action="store_true", help="really delete (no prompt)")
    args = parser.parse_args()
    if not args.yes:
        print("This deletes all conversations, proposed actions and CRM changes in the dev DB.")
        print("Run again with --yes to proceed.")
        return 2

    settings = get_settings()
    with SessionLocal() as session:
        result = reset_demo(session, settings.upload_dir, demo_filenames(DATA_DIR))
        session.commit()

    for path in result.files_to_remove:
        path.unlink(missing_ok=True)
        for parent in (path.parent, path.parent.parent):  # {workspace}/{document}/ dirs
            if parent != settings.upload_dir and parent.exists() and not any(parent.iterdir()):
                parent.rmdir()

    print("Deleted:  ", ", ".join(f"{n} {name}" for name, n in result.deleted.items()))
    print("Reseeded: ", ", ".join(f"{n} {name}" for name, n in result.reseeded.items()))
    if result.removed_documents:
        print("Removed uploaded documents:", ", ".join(result.removed_documents))
    print("Demo reset. Reload the browser.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
