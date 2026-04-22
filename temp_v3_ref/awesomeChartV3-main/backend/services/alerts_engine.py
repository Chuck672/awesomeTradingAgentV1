from __future__ import annotations

import datetime as dt
import time
from typing import Any, Dict, Optional

import asyncio

from backend.services.historical import historical_service
from backend.services.alerts_store import get_enabled_alerts, append_event, update_state, init_tables
from backend.services.telegram import send_telegram_message


def _utc_day_key(ts: int) -> str:
    d = dt.datetime.utcfromtimestamp(int(ts)).date()
    return d.isoformat()


def _utc_midnight(ts: int) -> int:
    d = dt.datetime.utcfromtimestamp(int(ts)).date()
    return int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp())


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


def eval_london_break_asia_high_volume(rule: Dict[str, Any], state: Dict[str, Any]) -> Optional[str]:
    """
    rule:
      {
        "type": "london_break_asia_high_volume",
        "symbol": "EURUSD",
        "timeframe": "M5",
        "volume_mult": 1.5,
        "telegram": {"token":"..","chat_id":".."}   # optional
      }
    """
    symbol = str(rule.get("symbol") or "").strip()
    timeframe = str(rule.get("timeframe") or "").strip()
    vol_mult = _safe_float(rule.get("volume_mult") or 1.5, 1.5)
    if not symbol or not timeframe:
        return None

    # 用当前最新 bar 的时间作为“今天”
    latest = historical_service.get_history(symbol, timeframe, before_time=0, limit=2)
    if not latest or len(latest) < 2:
        return None

    last = latest[-1]
    prev = latest[-2]
    last_t = _safe_int(last.get("time"))
    if last_t <= 0:
        return None

    # 仅在伦敦时段（UTC 08:00-16:00）内触发
    day0 = _utc_midnight(last_t)
    asia_start = day0 + 0 * 3600
    asia_end = day0 + 8 * 3600
    london_start = day0 + 8 * 3600
    london_end = day0 + 16 * 3600
    if not (london_start <= last_t <= london_end):
        return None

    # 去重：同一天只触发一次
    day_key = _utc_day_key(last_t)
    if str(state.get("last_trigger_day") or "") == day_key:
        return None

    bars_today = historical_service.get_history_range(symbol, timeframe, from_time=asia_start, to_time=min(last_t, london_end), limit=5000)
    if not bars_today:
        return None

    asia_bars = [b for b in bars_today if asia_start <= _safe_int(b.get("time")) <= asia_end]
    if not asia_bars:
        return None

    asia_high = max(_safe_float(b.get("high")) for b in asia_bars)
    asia_vols = [_safe_float(b.get("tick_volume") or b.get("volume") or 0.0) for b in asia_bars]
    asia_avg_vol = sum(asia_vols) / max(1, len(asia_vols))

    last_close = _safe_float(last.get("close"))
    prev_close = _safe_float(prev.get("close"))
    last_vol = _safe_float(last.get("tick_volume") or last.get("volume") or 0.0)

    if prev_close <= asia_high and last_close > asia_high and (asia_avg_vol <= 0 or last_vol >= vol_mult * asia_avg_vol):
        msg = (
            f"*Alert* London breakout Asia high\\n"
            f"- {symbol} {timeframe}\\n"
            f"- AsiaHigh: {asia_high:.3f}\\n"
            f"- Close: {last_close:.3f}\\n"
            f"- Vol: {last_vol:.0f} (asia_avg {asia_avg_vol:.0f}, x{vol_mult})\\n"
            f"- Time(UTC): {dt.datetime.utcfromtimestamp(last_t).isoformat()}Z"
        )
        return msg

    return None


def eval_once() -> None:
    init_tables()
    alerts = get_enabled_alerts()
    for a in alerts:
        aid = int(a["id"])
        rule = a.get("rule") or {}
        state = a.get("state") or {}
        typ = str(rule.get("type") or "")
        msg = None
        if typ == "london_break_asia_high_volume":
            msg = eval_london_break_asia_high_volume(rule, state)
        else:
            continue

        if msg:
            append_event(aid, msg)
            # telegram (optional)
            tg = rule.get("telegram") if isinstance(rule.get("telegram"), dict) else {}
            token = str(tg.get("token") or "")
            chat_id = str(tg.get("chat_id") or "")
            if token and chat_id:
                try:
                    send_telegram_message(bot_token=token, chat_id=chat_id, text=msg)
                except Exception:
                    pass
            # update state（按触发 bar 的 UTC day 去重）
            t_now = int(time.time())
            update_state(aid, {"last_trigger_day": _utc_day_key(t_now), "last_trigger_ts": t_now})


async def loop(interval_sec: int = 30) -> None:
    while True:
        try:
            eval_once()
        except Exception:
            pass
        await asyncio.sleep(interval_sec)
