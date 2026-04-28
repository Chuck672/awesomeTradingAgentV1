import sqlite3
import contextlib
import time

@contextlib.contextmanager
def get_db_conn(db_path):
    for _ in range(10):
        try:
            with contextlib.closing(sqlite3.connect(db_path, timeout=30.0)) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                yield conn
            return
        except sqlite3.OperationalError as e:
            if "unable to open database file" in str(e) or "database is locked" in str(e):
                time.sleep(0.1)
            else:
                raise
    raise sqlite3.OperationalError(f"Failed to open {db_path} after 10 retries")
import os
import logging
from typing import List, Dict, Any, Optional
import asyncio
import json
import time
from backend.database.app_config import app_config

logger = logging.getLogger(__name__)

class SQLiteManager:
    """
    Unified SQLite manager for all broker data: OHLCV, metadata, and scene/strategy states.
    Replaces DuckDB, ParquetStore, and BrokerMetaStore.
    """
    def __init__(self, broker_id: str):
        self.broker_id = broker_id
        self.sandbox_dir = os.path.join(app_config.get_brokers_dir(), broker_id)
        os.makedirs(self.sandbox_dir, exist_ok=True)
        self.db_path = os.path.join(self.sandbox_dir, "data.sqlite")
        self.write_lock = asyncio.Lock()
        

        self._init_db()




    def _init_db(self):
        with get_db_conn(self.db_path) as conn, conn:
            cursor = conn.cursor()
            
            # 1. Active Symbols (from BrokerMetaStore)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS active_symbols (
                    symbol TEXT PRIMARY KEY,
                    timeframes TEXT,
                    is_active INTEGER DEFAULT 1
                )
            """)
            
            # 2. Sync State (from BrokerMetaStore)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sync_state (
                    symbol TEXT,
                    timeframe TEXT,
                    last_sync_time INTEGER,
                    last_archived_month TEXT,
                    PRIMARY KEY (symbol, timeframe)
                )
            """)
            
            # 3. OHLCV Data (from DuckDB ohlcv_hot)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ohlcv (
                    symbol TEXT,
                    timeframe TEXT,
                    time INTEGER,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    tick_volume INTEGER,
                    delta_volume INTEGER,
                    source TEXT,
                    PRIMARY KEY (symbol, timeframe, time)
                )
            """)
            
            # 4. Scene Snapshots
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scene_snapshots (
                    symbol TEXT,
                    timeframe TEXT,
                    time INTEGER,
                    snapshot_id TEXT,
                    state_hash TEXT,
                    scene_json TEXT,
                    PRIMARY KEY(symbol, timeframe, time)
                )
            """)
            
            # 5. Runtime States
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS runtime_states (
                    symbol TEXT,
                    timeframe TEXT,
                    updated_at INTEGER,
                    state_json TEXT,
                    PRIMARY KEY(symbol, timeframe)
                )
            """)
            
            # 6. Strategy Annotations
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS strategy_annotations (
                    symbol TEXT,
                    timeframe TEXT,
                    trigger_time INTEGER,
                    rule_id TEXT,
                    candidate_key TEXT,
                    version INTEGER,
                    is_active INTEGER,
                    created_at INTEGER,
                    updated_at INTEGER,
                    snapshot_id TEXT,
                    data_version TEXT,
                    evidence_json TEXT,
                    annotation_json TEXT,
                    PRIMARY KEY(candidate_key, version)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_strategy_annotations_key ON strategy_annotations(candidate_key)")
            
            # 7. Strategy Gate Decisions
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS strategy_gate_decisions (
                    symbol TEXT,
                    timeframe TEXT,
                    trigger_time INTEGER,
                    rule_id TEXT,
                    candidate_key TEXT,
                    version INTEGER,
                    is_active INTEGER,
                    created_at INTEGER,
                    updated_at INTEGER,
                    snapshot_id TEXT,
                    data_version TEXT,
                    annotation_version INTEGER,
                    decision_json TEXT,
                    trade_plan_json TEXT,
                    PRIMARY KEY(candidate_key, version)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_strategy_gate_key ON strategy_gate_decisions(candidate_key)")
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trade_deals (
                    account_id TEXT,
                    ticket INTEGER,
                    time INTEGER,
                    symbol TEXT,
                    type INTEGER,
                    entry INTEGER,
                    volume REAL,
                    price REAL,
                    profit REAL,
                    commission REAL,
                    swap REAL,
                    position_id INTEGER,
                    comment TEXT,
                    raw_json TEXT,
                    PRIMARY KEY(account_id, ticket)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trade_deals_time ON trade_deals(account_id, time)")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trade_daily (
                    account_id TEXT,
                    day TEXT,
                    pl REAL,
                    trades INTEGER,
                    winning_trades INTEGER,
                    gross_profit REAL,
                    gross_loss REAL,
                    fees REAL,
                    PRIMARY KEY(account_id, day)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trade_daily_day ON trade_daily(account_id, day)")

            conn.commit()

    # ==========================================
    # Meta Store API
    # ==========================================
    def add_symbol(self, symbol: str, timeframes: List[str] = ["M1", "M5", "M15", "H1"]):
        with get_db_conn(self.db_path) as conn, conn:
            cursor = conn.cursor()
            tf_json = json.dumps(timeframes)
            cursor.execute("""
                INSERT INTO active_symbols (symbol, timeframes, is_active)
                VALUES (?, ?, 1)
                ON CONFLICT(symbol) DO UPDATE SET timeframes=excluded.timeframes, is_active=1
            """, (symbol, tf_json))
            conn.commit()
            logger.info(f"Added active symbol: {symbol} {timeframes}")

    def clear_all_symbols(self):
        with get_db_conn(self.db_path) as conn, conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM active_symbols")
            cursor.execute("DELETE FROM sync_state")
            conn.commit()
            logger.info("Cleared all active symbols and sync states")

    def get_active_symbols(self) -> Dict[str, List[str]]:
        with get_db_conn(self.db_path) as conn, conn:
            cursor = conn.cursor()
            cursor.execute("SELECT symbol, timeframes FROM active_symbols WHERE is_active = 1")
            rows = cursor.fetchall()
            result = {}
            for row in rows:
                try:
                    result[row[0]] = json.loads(row[1])
                except json.JSONDecodeError:
                    result[row[0]] = []
            return result

    def update_sync_state(self, symbol: str, timeframe: str, last_time: int):
        try:
            with get_db_conn(self.db_path) as conn, conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO sync_state (symbol, timeframe, last_sync_time)
                    VALUES (?, ?, ?)
                    ON CONFLICT(symbol, timeframe) DO UPDATE SET last_sync_time=excluded.last_sync_time
                """, (symbol, timeframe, last_time))
                conn.commit()
        except Exception as e:
            logger.error(f"Error in update_sync_state opening {self.db_path}: {e}")
            logger.error(f"Environment APPDATA: {os.environ.get('APPDATA')}")
            logger.error(f"Does file exist? {os.path.exists(self.db_path)}")
            raise

    def get_sync_state(self, symbol: str, timeframe: str) -> Optional[int]:
        with get_db_conn(self.db_path) as conn, conn:
            cursor = conn.cursor()
            cursor.execute("SELECT last_sync_time FROM sync_state WHERE symbol = ? AND timeframe = ?", (symbol, timeframe))
            row = cursor.fetchone()
            return row[0] if row else None

    def update_archive_state(self, symbol: str, timeframe: str, archive_month: str):
        with get_db_conn(self.db_path) as conn, conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sync_state (symbol, timeframe, last_archived_month)
                VALUES (?, ?, ?)
                ON CONFLICT(symbol, timeframe) DO UPDATE SET last_archived_month=excluded.last_archived_month
            """, (symbol, timeframe, archive_month))
            conn.commit()

    def get_archive_state(self, symbol: str, timeframe: str) -> Optional[str]:
        with get_db_conn(self.db_path) as conn, conn:
            cursor = conn.cursor()
            cursor.execute("SELECT last_archived_month FROM sync_state WHERE symbol = ? AND timeframe = ?", (symbol, timeframe))
            row = cursor.fetchone()
            return row[0] if row else None

    # ==========================================
    # OHLCV API
    # ==========================================
    async def upsert_bars(self, bars: List[Dict[str, Any]]):
        if not bars:
            return
        
        stmt = """
            INSERT INTO ohlcv (symbol, timeframe, time, open, high, low, close, tick_volume, delta_volume, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (symbol, timeframe, time) DO UPDATE SET 
                open=EXCLUDED.open,
                high=EXCLUDED.high,
                low=EXCLUDED.low,
                close=EXCLUDED.close,
                tick_volume=EXCLUDED.tick_volume,
                delta_volume=EXCLUDED.delta_volume,
                source=EXCLUDED.source
        """
        records = [
            (
                b['symbol'], b['timeframe'], b['time'],
                b['open'], b['high'], b['low'], b['close'],
                b.get('tick_volume', 0), b.get('delta_volume', 0),
                b.get('source', 'unknown')
            )
            for b in bars
        ]
        
        async with self.write_lock:
            def _exec():
                with get_db_conn(self.db_path) as conn, conn:
                    conn.executemany(stmt, records)
                    conn.commit()
            try:
                await asyncio.to_thread(_exec)
            except Exception as e:
                logger.error(f"Failed to upsert bars to SQLite: {e}")

    def get_time_range(self, symbol: str, timeframe: str) -> Dict[str, Optional[int]]:
        with get_db_conn(self.db_path) as conn, conn:
            cursor = conn.cursor()
            cursor.execute("SELECT MIN(time), MAX(time) FROM ohlcv WHERE symbol = ? AND timeframe = ?", (symbol, timeframe))
            result = cursor.fetchone()
            return {'min_time': result[0] if result else None, 'max_time': result[1] if result else None}

    def fetch_hot_data(self, symbol: str, timeframe: str, since: int = 0) -> List[Dict[str, Any]]:
        with get_db_conn(self.db_path) as conn, conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT time, open, high, low, close, tick_volume, delta_volume, source
                FROM ohlcv
                WHERE symbol = ? AND timeframe = ? AND time >= ?
                ORDER BY time ASC
            """, (symbol, timeframe, since))
            
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    # ==========================================
    # Scene Snapshot / Runtime State API
    # ==========================================
    async def upsert_scene_snapshot(self, symbol: str, timeframe: str, ts: int, snapshot_id: str, state_hash: str, scene_json: str) -> None:
        stmt = """
            INSERT INTO scene_snapshots(symbol, timeframe, time, snapshot_id, state_hash, scene_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, timeframe, time) DO UPDATE SET
                snapshot_id=excluded.snapshot_id,
                state_hash=excluded.state_hash,
                scene_json=excluded.scene_json
        """
        async with self.write_lock:
            def _exec():
                with get_db_conn(self.db_path) as conn, conn:
                    conn.execute(stmt, (symbol, timeframe, int(ts), snapshot_id, state_hash, scene_json))
                    conn.commit()
            await asyncio.to_thread(_exec)

    async def upsert_runtime_state(self, symbol: str, timeframe: str, updated_at: int, state_json: str) -> None:
        stmt = """
            INSERT INTO runtime_states(symbol, timeframe, updated_at, state_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(symbol, timeframe) DO UPDATE SET
                updated_at=excluded.updated_at,
                state_json=excluded.state_json
        """
        async with self.write_lock:
            def _exec():
                with get_db_conn(self.db_path) as conn, conn:
                    conn.execute(stmt, (symbol, timeframe, int(updated_at), state_json))
                    conn.commit()
            await asyncio.to_thread(_exec)

    def get_runtime_state(self, symbol: str, timeframe: str) -> Optional[Dict[str, Any]]:
        with get_db_conn(self.db_path) as conn, conn:
            cursor = conn.cursor()
            row = cursor.execute("SELECT updated_at, state_json FROM runtime_states WHERE symbol = ? AND timeframe = ?", (symbol, timeframe)).fetchone()
            if not row:
                return None
            updated_at, state_json = row[0], row[1]
            state = state_json
            if isinstance(state, str):
                try:
                    state = json.loads(state)
                except Exception:
                    state = None
            if not isinstance(state, dict):
                return None
            state["_updated_at"] = int(updated_at) if updated_at else 0
            return state

    def query_scene_snapshots(
        self, symbol: str, timeframe: str, *, from_ts: int = 0, to_ts: int = 0, limit: int = 500, offset: int = 0, desc: bool = False
    ) -> List[Dict[str, Any]]:
        order = "DESC" if desc else "ASC"
        where = "WHERE symbol = ? AND timeframe = ?"
        params: List[Any] = [symbol, timeframe]
        if from_ts > 0:
            where += " AND time >= ?"
            params.append(int(from_ts))
        if to_ts > 0:
            where += " AND time <= ?"
            params.append(int(to_ts))

        q = f"SELECT time, snapshot_id, state_hash, scene_json FROM scene_snapshots {where} ORDER BY time {order} LIMIT ? OFFSET ?"
        params.extend([int(limit), int(offset)])

        with get_db_conn(self.db_path) as conn, conn:
            cursor = conn.cursor()
            cursor.execute(q, params)
            out: List[Dict[str, Any]] = []
            for r in cursor.fetchall():
                scene = r[3]
                if isinstance(scene, str):
                    try:
                        scene = json.loads(scene)
                    except Exception:
                        pass
                out.append({"time": int(r[0]), "snapshot_id": r[1], "state_hash": r[2], "scene": scene})
            return out

    def query_scene_snapshots_summary(
        self, symbol: str, timeframe: str, *, from_ts: int = 0, to_ts: int = 0, limit: int = 500, offset: int = 0, desc: bool = False
    ) -> List[Dict[str, Any]]:
        rows = self.query_scene_snapshots(symbol, timeframe, from_ts=from_ts, to_ts=to_ts, limit=limit, offset=offset, desc=desc)
        out: List[Dict[str, Any]] = []
        for r in rows:
            scene = r.get("scene") if isinstance(r.get("scene"), dict) else {}
            poc = (scene.get("poc_migration") or {}) if isinstance(scene, dict) else {}
            vp = (scene.get("volume_profile") or {}) if isinstance(scene, dict) else {}
            ctx = (scene.get("context") or {}) if isinstance(scene, dict) else {}

            ev_ids: List[str] = []
            try:
                for e in (vp.get("events") or [])[:50]:
                    ev_ids.append(str(e.get("id")))
            except Exception:
                ev_ids = []

            item = {
                "time": r.get("time"),
                "snapshot_id": r.get("snapshot_id"),
                "state_hash": r.get("state_hash"),
                "market_phase": ctx.get("market_phase"),
                "session": ctx.get("active_session"),
                "poc_state": poc.get("state"),
                "paths": poc.get("paths"),
                "entry_quality": (poc.get("scores") or {}).get("entry_quality") if isinstance(poc.get("scores"), dict) else None,
                "no_chase": (poc.get("scores") or {}).get("no_chase") if isinstance(poc.get("scores"), dict) else None,
                "next_actions": poc.get("next_actions"),
                "vp_event_ids": ev_ids,
            }
            out.append(item)
        return out

    def get_scene_by_time(
        self, symbol: str, timeframe: str, ts: int, *, mode: str = "nearest"
    ) -> Optional[Dict[str, Any]]:
        ts = int(ts)
        def _parse(row: Any) -> Optional[Dict[str, Any]]:
            if not row:
                return None
            t, snapshot_id, state_hash, scene_json = row[0], row[1], row[2], row[3]
            scene = scene_json
            if isinstance(scene, str):
                try:
                    scene = json.loads(scene)
                except Exception:
                    pass
            return {"time": int(t), "snapshot_id": snapshot_id, "state_hash": state_hash, "scene": scene}

        with get_db_conn(self.db_path) as conn, conn:
            cursor = conn.cursor()
            row = cursor.execute("SELECT time, snapshot_id, state_hash, scene_json FROM scene_snapshots WHERE symbol = ? AND timeframe = ? AND time = ? LIMIT 1", (symbol, timeframe, ts)).fetchone()
            if row: return _parse(row)

            left = cursor.execute("SELECT time, snapshot_id, state_hash, scene_json FROM scene_snapshots WHERE symbol = ? AND timeframe = ? AND time <= ? ORDER BY time DESC LIMIT 1", (symbol, timeframe, ts)).fetchone()

            if mode == "lte":
                if left: return _parse(left)
                right = cursor.execute("SELECT time, snapshot_id, state_hash, scene_json FROM scene_snapshots WHERE symbol = ? AND timeframe = ? AND time >= ? ORDER BY time ASC LIMIT 1", (symbol, timeframe, ts)).fetchone()
                return _parse(right)

            right = cursor.execute("SELECT time, snapshot_id, state_hash, scene_json FROM scene_snapshots WHERE symbol = ? AND timeframe = ? AND time >= ? ORDER BY time ASC LIMIT 1", (symbol, timeframe, ts)).fetchone()

            if not left and not right: return None
            if left and not right: return _parse(left)
            if right and not left: return _parse(right)
            dl = abs(int(left[0]) - ts)
            dr = abs(int(right[0]) - ts)
            return _parse(left if dl <= dr else right)

    # ==========================================
    # Strategy Annotations / Gate API
    # ==========================================
    def _candidate_key(self, symbol: str, timeframe: str, trigger_time: int, rule_id: str) -> str:
        return f"{symbol}|{timeframe}|{int(trigger_time)}|{rule_id}"

    async def list_strategy_annotations(self, symbol: str, timeframe: str, trigger_time: int, rule_id: str) -> Dict[str, Any]:
        key = self._candidate_key(symbol, timeframe, trigger_time, rule_id)
        def _q():
            with get_db_conn(self.db_path) as conn, conn:
                cursor = conn.cursor()
                cursor.execute("SELECT version, is_active, created_at, updated_at, snapshot_id, data_version, annotation_json FROM strategy_annotations WHERE candidate_key = ? ORDER BY version DESC", (key,))
                rows = cursor.fetchall()
                if not rows:
                    return {"candidate_key": key, "active_version": None, "versions": []}
                
                versions: List[Dict[str, Any]] = []
                active_version = None
                for r in rows:
                    v, is_active, created_at, updated_at, snapshot_id, data_version, ann_json = r
                    v = int(v or 0)
                    is_active = bool(is_active)
                    if is_active and active_version is None:
                        active_version = v
                    ann = json.loads(ann_json) if isinstance(ann_json, str) else None
                    dv = json.loads(data_version) if isinstance(data_version, str) else None
                    versions.append({
                        "version": v, "is_active": is_active, "created_at": int(created_at or 0),
                        "updated_at": int(updated_at or 0), "snapshot_id": snapshot_id,
                        "data_version": dv, "annotation": ann,
                    })
                return {"candidate_key": key, "active_version": active_version, "versions": versions}
        return await asyncio.to_thread(_q)

    async def save_strategy_annotation(
        self, *, symbol: str, timeframe: str, trigger_time: int, rule_id: str, snapshot_id: str,
        data_version: Dict[str, Any], evidence: Dict[str, Any], annotation: Dict[str, Any], set_active: bool = True
    ) -> Dict[str, Any]:
        key = self._candidate_key(symbol, timeframe, trigger_time, rule_id)
        now = int(time.time())
        async with self.write_lock:
            def _exec():
                with get_db_conn(self.db_path) as conn, conn:
                    cursor = conn.cursor()
                    row = cursor.execute("SELECT MAX(version) FROM strategy_annotations WHERE candidate_key = ?", (key,)).fetchone()
                    mx = int(row[0] or 0) if row and row[0] else 0
                    v = mx + 1
                    if set_active:
                        cursor.execute("UPDATE strategy_annotations SET is_active = 0 WHERE candidate_key = ?", (key,))
                    stmt = """
                        INSERT INTO strategy_annotations(
                            symbol, timeframe, trigger_time, rule_id, candidate_key,
                            version, is_active, created_at, updated_at,
                            snapshot_id, data_version, evidence_json, annotation_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    cursor.execute(stmt, (
                        str(symbol), str(timeframe), int(trigger_time), str(rule_id), key,
                        v, int(set_active), now, now, str(snapshot_id or ""),
                        json.dumps(data_version or {}, ensure_ascii=False),
                        json.dumps(evidence or {}, ensure_ascii=False),
                        json.dumps(annotation or {}, ensure_ascii=False),
                    ))
                    conn.commit()
                    return v
            v = await asyncio.to_thread(_exec)
        return {"candidate_key": key, "version": v, "is_active": bool(set_active), "created_at": now, "updated_at": now}

    async def set_active_strategy_annotation(self, *, symbol: str, timeframe: str, trigger_time: int, rule_id: str, version: int) -> Dict[str, Any]:
        key = self._candidate_key(symbol, timeframe, trigger_time, rule_id)
        now = int(time.time())
        version = int(version)
        async with self.write_lock:
            def _exec():
                with get_db_conn(self.db_path) as conn, conn:
                    cursor = conn.cursor()
                    cursor.execute("UPDATE strategy_annotations SET is_active = 0 WHERE candidate_key = ?", (key,))
                    cursor.execute("UPDATE strategy_annotations SET is_active = 1, updated_at = ? WHERE candidate_key = ? AND version = ?", (now, key, version))
                    conn.commit()
            await asyncio.to_thread(_exec)
        return {"candidate_key": key, "active_version": version, "updated_at": now}

    async def list_strategy_gate_decisions(self, symbol: str, timeframe: str, trigger_time: int, rule_id: str) -> Dict[str, Any]:
        key = self._candidate_key(symbol, timeframe, trigger_time, rule_id)
        def _q():
            with get_db_conn(self.db_path) as conn, conn:
                cursor = conn.cursor()
                cursor.execute("SELECT version, is_active, created_at, updated_at, snapshot_id, data_version, annotation_version, decision_json, trade_plan_json FROM strategy_gate_decisions WHERE candidate_key = ? ORDER BY version DESC", (key,))
                rows = cursor.fetchall()
                if not rows:
                    return {"candidate_key": key, "active_version": None, "versions": []}
                
                versions: List[Dict[str, Any]] = []
                active_version = None
                for r in rows:
                    v, is_active, created_at, updated_at, snapshot_id, dv_json, ann_v, dec_json, tp_json = r
                    v = int(v or 0)
                    is_active = bool(is_active)
                    if is_active and active_version is None:
                        active_version = v
                    versions.append({
                        "version": v, "is_active": is_active, "created_at": int(created_at or 0),
                        "updated_at": int(updated_at or 0), "snapshot_id": snapshot_id,
                        "data_version": json.loads(dv_json) if isinstance(dv_json, str) else None,
                        "annotation_version": int(ann_v) if ann_v else None,
                        "decision": json.loads(dec_json) if isinstance(dec_json, str) else None,
                        "trade_plan": json.loads(tp_json) if isinstance(tp_json, str) else None,
                    })
                return {"candidate_key": key, "active_version": active_version, "versions": versions}
        return await asyncio.to_thread(_q)

    async def save_strategy_gate_decision(
        self, *, symbol: str, timeframe: str, trigger_time: int, rule_id: str, snapshot_id: str,
        data_version: Dict[str, Any], annotation_version: Optional[int], decision: Dict[str, Any], trade_plan: Dict[str, Any], set_active: bool = True
    ) -> Dict[str, Any]:
        key = self._candidate_key(symbol, timeframe, trigger_time, rule_id)
        now = int(time.time())
        async with self.write_lock:
            def _exec():
                with get_db_conn(self.db_path) as conn, conn:
                    cursor = conn.cursor()
                    row = cursor.execute("SELECT MAX(version) FROM strategy_gate_decisions WHERE candidate_key = ?", (key,)).fetchone()
                    mx = int(row[0] or 0) if row and row[0] else 0
                    v = mx + 1
                    if set_active:
                        cursor.execute("UPDATE strategy_gate_decisions SET is_active = 0 WHERE candidate_key = ?", (key,))
                    stmt = """
                        INSERT INTO strategy_gate_decisions(
                            symbol, timeframe, trigger_time, rule_id, candidate_key,
                            version, is_active, created_at, updated_at,
                            snapshot_id, data_version, annotation_version, decision_json, trade_plan_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    cursor.execute(stmt, (
                        str(symbol), str(timeframe), int(trigger_time), str(rule_id), key,
                        v, int(set_active), now, now, str(snapshot_id or ""),
                        json.dumps(data_version or {}, ensure_ascii=False),
                        int(annotation_version) if annotation_version else None,
                        json.dumps(decision or {}, ensure_ascii=False),
                        json.dumps(trade_plan or {}, ensure_ascii=False),
                    ))
                    conn.commit()
                    return v
            v = await asyncio.to_thread(_exec)
        return {"candidate_key": key, "version": v, "is_active": bool(set_active), "created_at": now, "updated_at": now}

    async def set_active_strategy_gate_decision(self, *, symbol: str, timeframe: str, trigger_time: int, rule_id: str, version: int) -> Dict[str, Any]:
        key = self._candidate_key(symbol, timeframe, trigger_time, rule_id)
        now = int(time.time())
        version = int(version)
        async with self.write_lock:
            def _exec():
                with get_db_conn(self.db_path) as conn, conn:
                    cursor = conn.cursor()
                    cursor.execute("UPDATE strategy_gate_decisions SET is_active = 0 WHERE candidate_key = ?", (key,))
                    cursor.execute("UPDATE strategy_gate_decisions SET is_active = 1, updated_at = ? WHERE candidate_key = ? AND version = ?", (now, key, version))
                    conn.commit()
            await asyncio.to_thread(_exec)
        return {"candidate_key": key, "active_version": version, "updated_at": now}
