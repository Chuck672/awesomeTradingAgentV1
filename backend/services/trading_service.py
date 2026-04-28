from __future__ import annotations

import json
import time
import datetime as dt
from typing import Any, Dict, List, Optional, Tuple

from backend.api.dependencies import get_current_broker_deps
from backend.data_sources.mt5_source import MT5_AVAILABLE
from backend.database.sqlite_manager import get_db_conn

if MT5_AVAILABLE:
    import MetaTrader5 as mt5


def _day_str_utc(ts: int) -> str:
    return dt.datetime.utcfromtimestamp(int(ts)).strftime("%Y-%m-%d")


def _parse_day(day: str) -> Tuple[int, int]:
    d = dt.datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
    start = int(d.timestamp())
    end = int((d + dt.timedelta(days=1)).timestamp())
    return start, end


def _parse_date_range(from_day: str, to_day: str) -> Tuple[int, int]:
    s, _ = _parse_day(from_day)
    _, e = _parse_day(to_day)
    return s, e


def _get_account_id() -> str:
    if not MT5_AVAILABLE:
        return "no_mt5"
    info = mt5.account_info()
    if info is None:
        return "unknown"
    d = info._asdict() if hasattr(info, "_asdict") else dict(info)
    login = str(d.get("login") or "")
    server = str(d.get("server") or "")
    return f"{server}:{login}".strip(":") or "unknown"


def _ensure_broker_db_path() -> str:
    deps = get_current_broker_deps()
    if not deps:
        raise RuntimeError("No active broker configured")
    sqlite_manager = deps["sqlite_manager"]
    return str(sqlite_manager.db_path)


def sync_deals_range(*, from_ts: int, to_ts: int) -> Dict[str, Any]:
    if not MT5_AVAILABLE:
        raise RuntimeError("MT5 is not available")
    if to_ts <= from_ts:
        return {"account_id": _get_account_id(), "inserted": 0, "from_ts": from_ts, "to_ts": to_ts}

    account_id = _get_account_id()
    db_path = _ensure_broker_db_path()

    start_dt = dt.datetime.fromtimestamp(int(from_ts), tz=dt.timezone.utc)
    end_dt = dt.datetime.fromtimestamp(int(to_ts), tz=dt.timezone.utc)
    deals = mt5.history_deals_get(start_dt, end_dt)
    if deals is None:
        deals = []

    rows: List[Dict[str, Any]] = []
    for x in deals:
        d = x._asdict() if hasattr(x, "_asdict") else dict(x)
        rows.append(d)

    now = int(time.time())
    inserted = 0
    with get_db_conn(db_path) as conn, conn:
        cur = conn.cursor()
        for d in rows:
            ticket = int(d.get("ticket") or 0)
            if ticket <= 0:
                continue
            cur.execute(
                """
                INSERT INTO trade_deals (
                    account_id, ticket, time, symbol, type, entry, volume, price,
                    profit, commission, swap, position_id, comment, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_id, ticket) DO UPDATE SET
                    time=excluded.time,
                    symbol=excluded.symbol,
                    type=excluded.type,
                    entry=excluded.entry,
                    volume=excluded.volume,
                    price=excluded.price,
                    profit=excluded.profit,
                    commission=excluded.commission,
                    swap=excluded.swap,
                    position_id=excluded.position_id,
                    comment=excluded.comment,
                    raw_json=excluded.raw_json
                """,
                (
                    account_id,
                    ticket,
                    int(d.get("time") or 0),
                    str(d.get("symbol") or ""),
                    int(d.get("type") or 0),
                    int(d.get("entry") or 0),
                    float(d.get("volume") or 0.0),
                    float(d.get("price") or 0.0),
                    float(d.get("profit") or 0.0),
                    float(d.get("commission") or 0.0),
                    float(d.get("swap") or 0.0),
                    int(d.get("position_id") or 0),
                    str(d.get("comment") or ""),
                    json.dumps(d, ensure_ascii=False),
                ),
            )
            inserted += 1
        conn.commit()

    return {"account_id": account_id, "inserted": inserted, "from_ts": from_ts, "to_ts": to_ts, "ts": now}


def recompute_daily_agg(*, account_id: str, from_ts: int, to_ts: int) -> int:
    db_path = _ensure_broker_db_path()
    if to_ts <= from_ts:
        return 0

    with get_db_conn(db_path) as conn, conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT time, symbol, profit, commission, swap, position_id
            FROM trade_deals
            WHERE account_id = ? AND time >= ? AND time < ?
            ORDER BY time ASC
            """,
            (account_id, int(from_ts), int(to_ts)),
        )
        rows = cur.fetchall()

    by_day: Dict[str, Dict[str, Any]] = {}
    for (t, symbol, profit, commission, swap, position_id) in rows:
        if not symbol:
            continue
        day = _day_str_utc(int(t))
        pl = float(profit or 0.0) + float(commission or 0.0) + float(swap or 0.0)
        st = by_day.get(day)
        if st is None:
            st = {
                "pl": 0.0,
                "positions": {},
                "gross_profit": 0.0,
                "gross_loss": 0.0,
                "fees": 0.0,
            }
            by_day[day] = st
        st["pl"] += pl
        st["fees"] += float(commission or 0.0) + float(swap or 0.0)
        if pl > 0:
            st["gross_profit"] += pl
        elif pl < 0:
            st["gross_loss"] += abs(pl)
        pid = int(position_id or 0)
        if pid:
            st["positions"][pid] = st["positions"].get(pid, 0.0) + pl

    upserts = 0
    db_path = _ensure_broker_db_path()
    with get_db_conn(db_path) as conn, conn:
        cur = conn.cursor()
        for day, st in by_day.items():
            positions = st.get("positions") or {}
            trades = int(len(positions))
            winning = int(sum(1 for v in positions.values() if float(v) > 0))
            cur.execute(
                """
                INSERT INTO trade_daily (
                    account_id, day, pl, trades, winning_trades, gross_profit, gross_loss, fees
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_id, day) DO UPDATE SET
                    pl=excluded.pl,
                    trades=excluded.trades,
                    winning_trades=excluded.winning_trades,
                    gross_profit=excluded.gross_profit,
                    gross_loss=excluded.gross_loss,
                    fees=excluded.fees
                """,
                (
                    account_id,
                    day,
                    float(st.get("pl") or 0.0),
                    trades,
                    winning,
                    float(st.get("gross_profit") or 0.0),
                    float(st.get("gross_loss") or 0.0),
                    float(st.get("fees") or 0.0),
                ),
            )
            upserts += 1
        conn.commit()
    return upserts


def get_daily(*, from_day: str, to_day: str) -> Dict[str, Any]:
    from_ts, to_ts = _parse_date_range(from_day, to_day)
    sync_deals_range(from_ts=from_ts, to_ts=to_ts)
    account_id = _get_account_id()
    recompute_daily_agg(account_id=account_id, from_ts=from_ts, to_ts=to_ts)

    db_path = _ensure_broker_db_path()
    with get_db_conn(db_path) as conn, conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT day, pl, trades, winning_trades, gross_profit, gross_loss, fees
            FROM trade_daily
            WHERE account_id = ? AND day >= ? AND day <= ?
            ORDER BY day ASC
            """,
            (account_id, from_day, to_day),
        )
        rows = cur.fetchall()

    items = []
    for (day, pl, trades, winning, gp, gl, fees) in rows:
        items.append(
            {
                "day": str(day),
                "pl": float(pl or 0.0),
                "trades": int(trades or 0),
                "winning_trades": int(winning or 0),
                "gross_profit": float(gp or 0.0),
                "gross_loss": float(gl or 0.0),
                "fees": float(fees or 0.0),
            }
        )
    return {"ok": True, "account_id": account_id, "from": from_day, "to": to_day, "days": items}


def get_day_detail(*, day: str) -> Dict[str, Any]:
    from_ts, to_ts = _parse_day(day)
    sync_deals_range(from_ts=from_ts, to_ts=to_ts)
    account_id = _get_account_id()
    recompute_daily_agg(account_id=account_id, from_ts=from_ts, to_ts=to_ts)

    db_path = _ensure_broker_db_path()
    with get_db_conn(db_path) as conn, conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT ticket, time, symbol, type, entry, volume, price, profit, commission, swap, position_id, comment
            FROM trade_deals
            WHERE account_id = ? AND time >= ? AND time < ? AND symbol != ''
            ORDER BY time ASC
            """,
            (account_id, int(from_ts), int(to_ts)),
        )
        rows = cur.fetchall()
        cur.execute(
            "SELECT pl, trades, winning_trades, gross_profit, gross_loss, fees FROM trade_daily WHERE account_id = ? AND day = ?",
            (account_id, day),
        )
        daily = cur.fetchone()

    deals_out = []
    for (ticket, t, symbol, typ, entry, volume, price, profit, commission, swap, position_id, comment) in rows:
        deals_out.append(
            {
                "ticket": int(ticket or 0),
                "time": int(t or 0),
                "symbol": str(symbol or ""),
                "type": int(typ or 0),
                "entry": int(entry or 0),
                "volume": float(volume or 0.0),
                "price": float(price or 0.0),
                "profit": float(profit or 0.0),
                "commission": float(commission or 0.0),
                "swap": float(swap or 0.0),
                "pl": float(profit or 0.0) + float(commission or 0.0) + float(swap or 0.0),
                "position_id": int(position_id or 0),
                "comment": str(comment or ""),
            }
        )

    daily_out = None
    if daily:
        pl, trades, winning, gp, gl, fees = daily
        daily_out = {
            "day": day,
            "pl": float(pl or 0.0),
            "trades": int(trades or 0),
            "winning_trades": int(winning or 0),
            "gross_profit": float(gp or 0.0),
            "gross_loss": float(gl or 0.0),
            "fees": float(fees or 0.0),
        }

    return {"ok": True, "account_id": account_id, "day": day, "daily": daily_out, "deals": deals_out}


def build_rules_report(days: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_pl = sum(float(x.get("pl") or 0.0) for x in days)
    total_trades = sum(int(x.get("trades") or 0) for x in days)
    wins = sum(int(x.get("winning_trades") or 0) for x in days)
    gross_profit = sum(float(x.get("gross_profit") or 0.0) for x in days)
    gross_loss = sum(float(x.get("gross_loss") or 0.0) for x in days)
    fees = sum(float(x.get("fees") or 0.0) for x in days)
    win_rate = (wins / total_trades * 100.0) if total_trades > 0 else 0.0
    pf = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)

    issues: List[Dict[str, Any]] = []

    if total_trades > 0 and win_rate < 35.0:
        issues.append({"id": "low_win_rate", "severity": "warning", "title": "胜率偏低", "evidence": {"win_rate": win_rate, "trades": total_trades}})
    if gross_loss > 0 and pf < 1.2:
        issues.append({"id": "low_profit_factor", "severity": "warning", "title": "Profit Factor 偏低", "evidence": {"profit_factor": pf, "gross_profit": gross_profit, "gross_loss": gross_loss}})
    if total_trades > 0 and abs(fees) > abs(total_pl) * 0.35 and abs(total_pl) > 0:
        issues.append({"id": "fees_too_high", "severity": "info", "title": "手续费/隔夜费影响较大", "evidence": {"fees": fees, "net_pl": total_pl}})

    return {
        "summary": {
            "total_pl": total_pl,
            "total_trades": total_trades,
            "win_rate": win_rate,
            "profit_factor": pf,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "fees": fees,
        },
        "issues": issues,
    }

