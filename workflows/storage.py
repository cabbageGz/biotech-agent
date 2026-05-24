from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


RUN_ID_FORMAT = "%Y%m%d-%H%M%S"


class RunStorage:
    def __init__(self, root: Path | str = "database/runs") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def new_run_dir(self) -> Path:
        run_id = datetime.now().strftime(RUN_ID_FORMAT)
        path = self.root / run_id
        suffix = 1
        while path.exists():
            path = self.root / f"{run_id}-{suffix}"
            suffix += 1
        path.mkdir(parents=True)
        return path

    def write_run(self, run_dir: Path, payload: dict[str, Any], files: dict[str, str]) -> dict[str, Any]:
        for filename, content in files.items():
            (run_dir / filename).write_text(content, encoding="utf-8")
        payload = {
            **payload,
            "run_id": run_dir.name,
            "files": sorted(files),
        }
        (run_dir / "run.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    def list_runs(self, user_id: int | None = None) -> list[dict[str, Any]]:
        runs = []
        for run_dir in sorted(self.root.iterdir(), reverse=True):
            meta_path = run_dir / "run.json"
            if run_dir.is_dir() and meta_path.exists():
                payload = json.loads(meta_path.read_text(encoding="utf-8"))
                if user_id is None or payload.get("user_id") == user_id:
                    runs.append(payload)
        return runs

    def read_run(self, run_id: str) -> dict[str, Any]:
        run_dir = self.root / run_id
        meta_path = run_dir / "run.json"
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
        payload["file_contents"] = {}
        for filename in payload.get("files", []):
            path = run_dir / filename
            if path.exists():
                payload["file_contents"][filename] = path.read_text(encoding="utf-8")
        return payload

    def clear_runs(self, user_id: int | None = None) -> int:
        removed = 0
        for run_dir in self.root.iterdir():
            if run_dir.is_dir():
                if user_id is not None:
                    meta_path = run_dir / "run.json"
                    if not meta_path.exists():
                        continue
                    payload = json.loads(meta_path.read_text(encoding="utf-8"))
                    if payload.get("user_id") != user_id:
                        continue
                shutil.rmtree(run_dir)
                removed += 1
        return removed

    def update_run(self, run_id: str, updates: dict[str, Any], files: dict[str, str] | None = None) -> dict[str, Any]:
        run_dir = self.root / run_id
        meta_path = run_dir / "run.json"
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
        for filename, content in (files or {}).items():
            (run_dir / filename).write_text(content, encoding="utf-8")
        existing_files = set(payload.get("files", []))
        existing_files.update((files or {}).keys())
        payload.update(updates)
        payload["files"] = sorted(existing_files)
        meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.read_run(run_id)
