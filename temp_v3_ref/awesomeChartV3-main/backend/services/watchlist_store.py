from __future__ import annotations

import sqlite3
import time
from typing import List

from backend.database.app_config import app_config


def _conn():
    return sqlite3.connect(app_config.db_path)


def list_watchlist() -> List[str]:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS watchlist (symbol TEXT PRIMARY KEY, created_at INTEGER)")
        rows = cur.execute("SELECT symbol FROM watchlist ORDER BY created_at DESC").fetchall()
        return [r[0] for r in rows]


def add_symbol(symbol: str) -> None:
    s = (symbol or "").strip()
    if not s:
        return
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS watchlist (symbol TEXT PRIMARY KEY, created_at INTEGER)")
        cur.execute(
            "INSERT OR REPLACE INTO watchlist(symbol, created_at) VALUES(?, ?)",
            (s, int(time.time())),
        )
        conn.commit()


def remove_symbol(symbol: str) -> None:
    s = (symbol or "").strip()
    if not s:
        return
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS watchlist (symbol TEXT PRIMARY KEY, created_at INTEGER)")
        cur.execute("DELETE FROM watchlist WHERE symbol = ?", (s,))
        conn.commit()

