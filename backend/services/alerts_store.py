from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Dict, List, Optional

from backend.database.app_config import app_config


def _conn():
    return sqlite3.connect(app_config.db_path)


def init_tables() -> None:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS alerts (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT,
              rule_json TEXT,
              enabled INTEGER DEFAULT 1,
              state_json TEXT DEFAULT '{}',
              created_at INTEGER
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS alert_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              alert_id INTEGER,
              ts INTEGER,
              message TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_reports (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              alert_id INTEGER,
              session_id TEXT,
              ts INTEGER,
              report_content TEXT
            )
            """
        )
        conn.commit()


def list_alerts() -> List[Dict[str, Any]]:
    init_tables()
    with _conn() as conn:
        cur = conn.cursor()
        rows = cur.execute("SELECT id, name, rule_json, enabled, state_json, created_at FROM alerts ORDER BY id DESC").fetchall()
        out = []
        for r in rows:
            out.append(
                {
                    "id": r[0],
                    "name": r[1],
                    "rule": json.loads(r[2] or "{}"),
                    "enabled": bool(r[3]),
                    "state": json.loads(r[4] or "{}"),
                    "created_at": r[5],
                }
            )
        return out


def create_alert(name: str, rule: Dict[str, Any], enabled: bool = True) -> int:
    init_tables()
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO alerts(name, rule_json, enabled, state_json, created_at) VALUES(?,?,?,?,?)",
            (name, json.dumps(rule, ensure_ascii=False), 1 if enabled else 0, "{}", int(time.time())),
        )
        conn.commit()
        return int(cur.lastrowid)


def delete_alert(alert_id: int) -> None:
    init_tables()
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM alerts WHERE id = ?", (int(alert_id),))
        conn.commit()


def set_enabled(alert_id: int, enabled: bool) -> None:
    init_tables()
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE alerts SET enabled = ? WHERE id = ?", (1 if enabled else 0, int(alert_id)))
        conn.commit()


def update_state(alert_id: int, state: Dict[str, Any]) -> None:
    init_tables()
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE alerts SET state_json = ? WHERE id = ?", (json.dumps(state, ensure_ascii=False), int(alert_id)))
        conn.commit()


def append_event(alert_id: int, message: str) -> None:
    init_tables()
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO alert_events(alert_id, ts, message) VALUES(?,?,?)",
            (int(alert_id), int(time.time()), str(message)),
        )
        conn.commit()


def list_events(limit: int = 100) -> List[Dict[str, Any]]:
    init_tables()
    with _conn() as conn:
        cur = conn.cursor()
        rows = cur.execute(
            "SELECT id, alert_id, ts, message FROM alert_events ORDER BY id DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        return [{"id": r[0], "alert_id": r[1], "ts": r[2], "message": r[3]} for r in rows]

def save_ai_report(alert_id: int, session_id: str, report_content: str) -> None:
    init_tables()
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO ai_reports(alert_id, session_id, ts, report_content) VALUES(?,?,?,?)",
            (int(alert_id), str(session_id), int(time.time()), str(report_content)),
        )
        conn.commit()

def list_ai_reports(limit: int = 50) -> List[Dict[str, Any]]:
    init_tables()
    with _conn() as conn:
        cur = conn.cursor()
        rows = cur.execute(
            """
            SELECT r.id, r.alert_id, r.session_id, r.ts, r.report_content, a.name 
            FROM ai_reports r
            LEFT JOIN alerts a ON r.alert_id = a.id
            ORDER BY r.id DESC LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        return [{
            "id": r[0], 
            "alert_id": r[1], 
            "session_id": r[2], 
            "ts": r[3], 
            "report_content": r[4],
            "alert_name": r[5] or f"Alert #{r[1]}"
        } for r in rows]


def get_enabled_alerts() -> List[Dict[str, Any]]:
    init_tables()
    with _conn() as conn:
        cur = conn.cursor()
        rows = cur.execute("SELECT id, name, rule_json, state_json FROM alerts WHERE enabled = 1").fetchall()
        out = []
        for r in rows:
            out.append({"id": r[0], "name": r[1], "rule": json.loads(r[2] or "{}"), "state": json.loads(r[3] or "{}")})
        return out

