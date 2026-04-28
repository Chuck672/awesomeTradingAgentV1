from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@lru_cache(maxsize=8)
def _read_text_cached(path_str: str, mtime_ns: int) -> str:
    p = Path(path_str)
    return p.read_text(encoding="utf-8")


def load_alert_analyzer_prompt() -> str:
    try:
        from backend.services.alerts_store import get_analyzer_system_prompt

        db_text = (get_analyzer_system_prompt() or "").strip()
        if db_text:
            return db_text + "\n"
    except Exception:
        pass

    override = os.environ.get("AWESOMECHART_ALERT_ANALYZER_PROMPT_PATH", "").strip()
    p = Path(override) if override else (_repo_root() / "docs" / "Analyzer_prompts.md")
    try:
        mtime_ns = int(p.stat().st_mtime_ns)
    except Exception:
        mtime_ns = 0
    try:
        text = _read_text_cached(str(p), mtime_ns)
    except Exception:
        return ""
    text = (text or "").strip()
    return (text + "\n") if text else ""
