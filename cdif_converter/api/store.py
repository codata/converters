"""Per-upload working directories: stores original uploaded file, meta.json, and conversion outputs."""

from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from pathlib import Path


class UploadNotFound(KeyError):
    pass


class UploadStore:
    def __init__(self, root: Path, ttl_seconds: int) -> None:
        self.root = Path(root)
        self.ttl = ttl_seconds
        self.root.mkdir(parents=True, exist_ok=True)

    def _dir(self, file_id: str) -> Path:
        if not file_id.isalnum():
            raise UploadNotFound(file_id)
        return self.root / file_id

    def create(self, filename: str, content: bytes, meta: dict) -> tuple[str, Path]:
        file_id = uuid.uuid4().hex
        d = self._dir(file_id)
        d.mkdir(parents=True)
        safe_name = Path(filename).name or "upload"
        src = d / safe_name
        src.write_bytes(content)
        (d / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
        self._touch(d)
        return file_id, src

    def save_meta(self, file_id: str, meta: dict) -> None:
        d = self._dir(file_id)
        (d / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
        self._touch(d)

    @staticmethod
    def _touch(d: Path) -> None:
        try:
            os.utime(d)
        except OSError:
            pass

    def load_meta(self, file_id: str) -> dict:
        d = self._dir(file_id)
        meta_path = d / "meta.json"
        if not meta_path.exists():
            raise UploadNotFound(file_id)
        self._touch(d)
        return json.loads(meta_path.read_text(encoding="utf-8"))

    def get_source_file(self, file_id: str) -> Path:
        d = self._dir(file_id)
        meta = self.load_meta(file_id)
        src = d / meta.get("filename", "upload")
        if not src.exists():
            # Fallback to first non-meta file
            for f in d.iterdir():
                if f.name != "meta.json":
                    return f
            raise UploadNotFound(file_id)
        return src

    def delete(self, file_id: str) -> None:
        d = self._dir(file_id)
        if not d.exists():
            raise UploadNotFound(file_id)
        shutil.rmtree(d, ignore_errors=True)

    def cleanup_expired(self) -> int:
        now = time.time()
        removed = 0
        for d in self.root.iterdir():
            if d.is_dir() and now - d.stat().st_mtime > self.ttl:
                shutil.rmtree(d, ignore_errors=True)
                removed += 1
        return removed
