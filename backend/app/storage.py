"""Local file storage for uploaded sources.

Paths passed in and stored in the DB are relative to `root` (settings.upload_dir), so the
same DB rows work locally and in Docker. Swap this module for S3/GCS later if needed.
"""

from pathlib import Path


def _resolve(root: Path, relative_path: str) -> Path:
    root = root.resolve()
    path = (root / relative_path).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Path escapes storage root: {relative_path}")
    return path


def save_file(root: Path, relative_path: str, data: bytes) -> Path:
    path = _resolve(root, relative_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def read_file(root: Path, relative_path: str) -> bytes:
    return _resolve(root, relative_path).read_bytes()


def delete_file(root: Path, relative_path: str) -> None:
    _resolve(root, relative_path).unlink(missing_ok=True)
