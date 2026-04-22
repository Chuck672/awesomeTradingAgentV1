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


from backend.services.chart_scene.indicators import calc_raja_sr, calc_msb_zigzag
from backend.api.agent_routes import run_agent_workflow
import uuid

def _get_active_symbols() -> List[str]:
    # A helper to get actively tracked symbols. For simplicity, we can fetch from meta_store.
    from backend.services.ingestion import ingestion_service
    # If ingestion_service isn't fully tracking it this way, we can also query the DB
    return ["EURUSD"] # Fallback or dynamic fetch

def eval_ai_agent_triggers(rule: Dict[str, Any], state: Dict[str, Any]) -> Optional[str]:
    """
    rule:
      {
        "type": "ai_agent_trigger",
        "symbol": "EURUSD",
        "timeframe": "M15",
        "enable_raja_sr": True,
        "enable_msb": True,
        "agent_configs": {...} # Agent configurations
      }
    """
    symbol = str(rule.get("symbol") or "").strip()
    timeframe = str(rule.get("timeframe") or "").strip()
    if not symbol or not timeframe:
        return None

    bars = historical_service.get_history(symbol, timeframe, before_time=0, limit=400)
    if not bars or len(bars) < 50:
        return None
        
    last_bar = bars[-1]
    last_t = _safe_int(last_bar.get("time"))
    last_close = _safe_float(last_bar.get("close"))
    
    # 1. Check MSB ZigZag (No cooldown)
    if rule.get("enable_msb"):
        # We need swings to calculate MSB
        from backend.services.chart_scene.indicators import detect_swings, structure_state_from_swings
        highs = [float(b["high"]) for b in bars]
        lows = [float(b["low"]) for b in bars]
        swings = detect_swings(highs, lows, 5)
        state_msb = structure_state_from_swings(swings, last_close)
        
        # If there's a recent BOS or CHOCH on the last bar
        last_break = state.get("last_msb_break_time", 0)
        # Simplified check: if current trend just changed or a level was broken recently
        # For a real implementation, we'd check if the break happened exactly on `last_t`
        # Let's simulate a trigger if close breaks the last swing high/low
        if len(swings) >= 2:
            last_swing = swings[-1]
            if last_t != last_break:
                if (last_swing["type"] == "High" and last_close > last_swing["price"]) or \
                   (last_swing["type"] == "Low" and last_close < last_swing["price"]):
                    
                    state["last_msb_break_time"] = last_t
                    return f"MSB Trigger: Price {last_close} broke structure at {last_swing['price']}"

    # 2. Check RajaSR (30 min cooldown)
    if rule.get("enable_raja_sr"):
        zones = calc_raja_sr(bars, max_zones=5)
        last_raja_trigger = state.get("last_raja_trigger_time", 0)
        
        # 30 minute cooldown = 1800 seconds
        if (int(time.time()) - last_raja_trigger) > 1800:
            for zone in zones:
                # If price is inside or very close to the zone
                if zone["bottom"] <= last_close <= zone["top"]:
                    state["last_raja_trigger_time"] = int(time.time())
                    return f"RajaSR Trigger: Price {last_close} entered {zone['type']} zone ({zone['bottom']} - {zone['top']})"

    return None
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
        
        # Original rule
        if typ == "london_break_asia_high_volume":
            msg = eval_london_break_asia_high_volume(rule, state)
        
        # New AI Agent Event Triggers
        elif typ == "ai_agent_trigger":
            msg = eval_ai_agent_triggers(rule, state)
            if msg:
                # If triggered, spin up a background agent workflow!
                configs = rule.get("agent_configs", {})
                session_id = f"evt_{aid}_{uuid.uuid4().hex[:8]}"
                # Because we're in sync code right now, we can run it via asyncio create_task
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(run_agent_workflow(session_id, f"Auto-triggered event: {msg}. Please analyze context and execute.", configs))
                except Exception as e:
                    pass
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
            # update state (persist any state changes made during evaluation)
            t_now = int(time.time())
            state["last_trigger_day"] = _utc_day_key(t_now)
            state["last_trigger_ts"] = t_now
            update_state(aid, state)


async def loop(interval_sec: int = 30) -> None:
    while True:
        try:
            eval_once()
        except Exception:
            pass
        await asyncio.sleep(interval_sec)
