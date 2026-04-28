from __future__ import annotations

import json
import sqlite3
import time
import os
import contextlib
from typing import Any, Dict, List, Optional

from backend.database.app_config import app_config
from backend.database.app_config import get_db_conn


def _alerts_db_path() -> str:
    override = os.environ.get("AWESOMECHART_ALERTS_DB", "").strip()
    if override:
        os.makedirs(os.path.dirname(override) or ".", exist_ok=True)
        return override
    base_dir = app_config.get_base_dir()
    os.makedirs(base_dir, exist_ok=True)
    return os.path.join(base_dir, "alerts.sqlite")


def _redact_rule_for_api(rule: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(rule or {})
    tg = out.get("telegram")
    if isinstance(tg, dict):
        tg2 = dict(tg)
        if "token" in tg2 and tg2.get("token"):
            tg2["token"] = "********"
        out["telegram"] = tg2
    return out


def _create_tables(conn: sqlite3.Connection) -> None:
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
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS alert_ai_decision_state (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          alert_id INTEGER,
          symbol TEXT,
          exec_tf TEXT,
          state_json TEXT,
          updated_at INTEGER,
          UNIQUE(alert_id, symbol, exec_tf)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS alert_kv (
          key TEXT PRIMARY KEY,
          value_text TEXT,
          updated_at INTEGER
        )
        """
    )
    conn.commit()


def _maybe_migrate_from_app_config_db() -> None:
    new_path = _alerts_db_path()
    if os.path.exists(new_path) and os.path.getsize(new_path) > 0:
        return

    old_path = app_config.db_path
    if not os.path.exists(old_path):
        return

    try:
        with get_db_conn(old_path) as old_conn:
            cur = old_conn.cursor()
            has_alerts = cur.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='alerts' LIMIT 1"
            ).fetchone()
            if not has_alerts:
                return
            alerts_rows = cur.execute(
                "SELECT id, name, rule_json, enabled, state_json, created_at FROM alerts"
            ).fetchall()
            events_rows = cur.execute(
                "SELECT id, alert_id, ts, message FROM alert_events"
            ).fetchall()
            reports_rows = cur.execute(
                "SELECT id, alert_id, session_id, ts, report_content FROM ai_reports"
            ).fetchall()
    except Exception:
        return

    if not alerts_rows and not events_rows and not reports_rows:
        return

    try:
        with get_db_conn(new_path) as new_conn:
            _create_tables(new_conn)
            cur = new_conn.cursor()
            if alerts_rows:
                cur.executemany(
                    "INSERT INTO alerts(id, name, rule_json, enabled, state_json, created_at) VALUES(?,?,?,?,?,?)",
                    alerts_rows,
                )
            if events_rows:
                cur.executemany(
                    "INSERT INTO alert_events(id, alert_id, ts, message) VALUES(?,?,?,?)",
                    events_rows,
                )
            if reports_rows:
                cur.executemany(
                    "INSERT INTO ai_reports(id, alert_id, session_id, ts, report_content) VALUES(?,?,?,?,?)",
                    reports_rows,
                )
            new_conn.commit()
    except Exception:
        return


@contextlib.contextmanager
def _conn():
    db_path = _alerts_db_path()
    with get_db_conn(db_path) as conn:
        try:
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA busy_timeout=30000;")
        except Exception:
            pass
        yield conn


def init_tables() -> None:
    _maybe_migrate_from_app_config_db()
    with _conn() as conn:
        _create_tables(conn)


def list_alerts() -> List[Dict[str, Any]]:
    init_tables()
    with _conn() as conn:
        cur = conn.cursor()
        rows = cur.execute("SELECT id, name, rule_json, enabled, state_json, created_at FROM alerts ORDER BY id DESC").fetchall()
        out = []
        for r in rows:
            try:
                rule = json.loads(r[2] or "{}")
            except Exception:
                rule = {}
            try:
                state = json.loads(r[4] or "{}")
            except Exception:
                state = {}
            out.append(
                {
                    "id": r[0],
                    "name": r[1],
                    "rule": _redact_rule_for_api(rule) if isinstance(rule, dict) else {},
                    "enabled": bool(r[3]),
                    "state": state,
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


def clear_events(alert_id: int | None = None) -> int:
    init_tables()
    with _conn() as conn:
        cur = conn.cursor()
        if alert_id is None:
            cur.execute("DELETE FROM alert_events")
        else:
            cur.execute("DELETE FROM alert_events WHERE alert_id = ?", (int(alert_id),))
        n = int(cur.rowcount or 0)
        conn.commit()
        return n


def save_ai_report(alert_id: int, session_id: str, report_content: str) -> None:
    init_tables()
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO ai_reports(alert_id, session_id, ts, report_content) VALUES(?,?,?,?)",
            (int(alert_id), str(session_id), int(time.time()), str(report_content)),
        )
        conn.commit()


def clear_ai_reports(alert_id: int | None = None) -> int:
    init_tables()
    with _conn() as conn:
        cur = conn.cursor()
        if alert_id is None:
            cur.execute("DELETE FROM ai_reports")
        else:
            cur.execute("DELETE FROM ai_reports WHERE alert_id = ?", (int(alert_id),))
        n = int(cur.rowcount or 0)
        conn.commit()
        return n


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


def get_analyzer_system_prompt() -> str:
    init_tables()
    with _conn() as conn:
        cur = conn.cursor()
        row = cur.execute("SELECT value_text FROM alert_kv WHERE key = ? LIMIT 1", ("analyzer_system_prompt",)).fetchone()
        if not row:
            return ""
        return str(row[0] or "")


def set_analyzer_system_prompt(prompt: str) -> None:
    init_tables()
    text = str(prompt or "")
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO alert_kv(key, value_text, updated_at) VALUES(?,?,?)
            ON CONFLICT(key) DO UPDATE SET value_text=excluded.value_text, updated_at=excluded.updated_at
            """,
            ("analyzer_system_prompt", text, int(time.time())),
        )
        conn.commit()


def get_enabled_alerts() -> List[Dict[str, Any]]:
    init_tables()
    with _conn() as conn:
        cur = conn.cursor()
        rows = cur.execute("SELECT id, name, rule_json, state_json FROM alerts WHERE enabled = 1").fetchall()
        out = []
        for r in rows:
            try:
                rule = json.loads(r[2] or "{}")
            except Exception:
                rule = {}
            try:
                state = json.loads(r[3] or "{}")
            except Exception:
                state = {}
            out.append({"id": r[0], "name": r[1], "rule": rule, "state": state})
        return out


def get_ai_decision_state(alert_id: int, symbol: str, exec_tf: str) -> Dict[str, Any] | None:
    init_tables()
    with _conn() as conn:
        cur = conn.cursor()
        row = cur.execute(
            "SELECT state_json FROM alert_ai_decision_state WHERE alert_id = ? AND symbol = ? AND exec_tf = ? LIMIT 1",
            (int(alert_id), str(symbol), str(exec_tf)),
        ).fetchone()
        if not row:
            return None
        try:
            v = json.loads(row[0] or "{}")
        except Exception:
            return None
        return v if isinstance(v, dict) else None


def save_ai_decision_state(alert_id: int, symbol: str, exec_tf: str, state: Dict[str, Any]) -> None:
    init_tables()
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO alert_ai_decision_state(alert_id, symbol, exec_tf, state_json, updated_at)
            VALUES(?,?,?,?,?)
            ON CONFLICT(alert_id, symbol, exec_tf) DO UPDATE SET
              state_json=excluded.state_json,
              updated_at=excluded.updated_at
            """,
            (
                int(alert_id),
                str(symbol),
                str(exec_tf),
                json.dumps(state or {}, ensure_ascii=False),
                int(time.time()),
            ),
        )
        conn.commit()
