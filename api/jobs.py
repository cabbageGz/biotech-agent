from __future__ import annotations

import json
import os
import threading
import traceback
import uuid
from json import JSONDecodeError
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


class JobStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def create(self, user: dict[str, object], name: str) -> dict[str, Any]:
        job = {
            "id": uuid.uuid4().hex,
            "name": name,
            "status": "pending",
            "step": "任务已创建，等待执行...",
            "progress": 0,
            "user_id": int(user["id"]),
            "username": str(user.get("username") or ""),
            "run_id": "",
            "error": "",
            "result": {},
            "created_at": self._now(),
            "updated_at": self._now(),
        }
        self._write(job)
        return job

    def get(self, job_id: str) -> dict[str, Any]:
        path = self._path(job_id)
        if not path.exists():
            raise FileNotFoundError("任务不存在")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except JSONDecodeError:
            with self._lock:
                return json.loads(path.read_text(encoding="utf-8"))

    def can_access(self, job: dict[str, Any], user: dict[str, object]) -> bool:
        return user.get("role") == "admin" or int(job.get("user_id") or -1) == int(user["id"])

    def update(self, job_id: str, **updates: Any) -> dict[str, Any]:
        with self._lock:
            job = self.get(job_id)
            job.update(updates)
            job["updated_at"] = self._now()
            self._write(job)
            return job

    def progress(self, job_id: str, step: str, progress: int, run_id: str = "") -> None:
        updates: dict[str, Any] = {
            "status": "running",
            "step": step,
            "progress": max(0, min(99, progress)),
        }
        if run_id:
            updates["run_id"] = run_id
        self.update(job_id, **updates)

    def start(
        self,
        job_id: str,
        target: Callable[[Callable[[str, int, str], None]], dict[str, Any]],
    ) -> None:
        def runner() -> None:
            try:
                self.update(job_id, status="running", step="开始执行...", progress=1)
                result = target(lambda step, progress, run_id="": self.progress(job_id, step, progress, run_id))
                run_id = str(result.get("run_id") or "")
                self.update(
                    job_id,
                    status="completed",
                    step="发布预览已生成",
                    progress=100,
                    run_id=run_id,
                    result=result,
                )
            except Exception as exc:
                self.update(
                    job_id,
                    status="failed",
                    step="执行失败",
                    error=f"{exc}",
                    traceback=traceback.format_exc(),
                    progress=100,
                )

        thread = threading.Thread(target=runner, name=f"job-{job_id[:8]}", daemon=True)
        thread.start()

    def _write(self, job: dict[str, Any]) -> None:
        with self._lock:
            path = self._path(str(job["id"]))
            temp_path = path.with_suffix(".tmp")
            temp_path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temp_path, path)

    def _path(self, job_id: str) -> Path:
        clean = "".join(char for char in job_id if char.isalnum() or char in "-_")
        return self.root / f"{clean}.json"

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
