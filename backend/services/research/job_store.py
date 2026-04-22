from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Dict, Optional


class JobStore:
    """
    轻量级任务存储（内存）。
    目标：避免 event-study / backtest / optimize 阻塞请求线程。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: Dict[str, Dict[str, Any]] = {}

    def create(self, kind: str, params: Dict[str, Any]) -> str:
        jid = str(uuid.uuid4())
        now = int(time.time())
        with self._lock:
            self._jobs[jid] = {
                "id": jid,
                "kind": kind,
                "status": "running",  # running|done|error
                "progress": 0.0,
                "message": "",
                "params": params,
                "result": None,
                "files": {},
                "stats": {},
                "started_at": now,
                "finished_at": None,
                "error": None,
            }
        return jid

    def update(self, jid: str, **patch: Any) -> None:
        with self._lock:
            if jid not in self._jobs:
                return
            self._jobs[jid].update(patch)

    def get(self, jid: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            j = self._jobs.get(jid)
            return dict(j) if isinstance(j, dict) else None

    def finish_ok(self, jid: str, result: Any, files: Dict[str, str]) -> None:
        now = int(time.time())
        self.update(jid, status="done", progress=1.0, result=result, files=files, finished_at=now)

    def finish_err(self, jid: str, err: str) -> None:
        now = int(time.time())
        self.update(jid, status="error", error=err, message=err, finished_at=now)

    def cleanup(self, *, max_age_sec: int = 3 * 3600) -> int:
        """
        清理已结束的旧任务，避免内存无限增长。
        - 只清理 status=done/error 且 finished_at 距今超过 max_age_sec 的任务
        - running 任务不清理
        返回：删除数量
        """
        now = int(time.time())
        removed = 0
        with self._lock:
            ids = list(self._jobs.keys())
            for jid in ids:
                j = self._jobs.get(jid) or {}
                if j.get("status") not in ("done", "error"):
                    continue
                finished_at = int(j.get("finished_at") or 0)
                if finished_at <= 0:
                    continue
                if now - finished_at >= int(max_age_sec):
                    self._jobs.pop(jid, None)
                    removed += 1
        return removed


job_store = JobStore()
