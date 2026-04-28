from __future__ import annotations

import datetime as dt
import time
import logging
from typing import Any, Dict, Optional, List

import asyncio

from backend.services.historical import historical_service
from backend.services.alerts_store import get_enabled_alerts, append_event, update_state, init_tables
from backend.services.telegram import send_telegram_message

logger = logging.getLogger(__name__)

_last_scan_log_ts: int = 0


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


from backend.domain.market.structure.raja_sr_calc import calc_raja_sr
from backend.domain.market.structure.msb import calc_msb_zigzag
from backend.domain.market.indicators.trend_exhaustion import calc_trend_exhaustion
from backend.services.workflows.alert_dual_agent_workflow import AlertDualAgentWorkflow
import uuid
import hashlib

def _get_active_symbols() -> List[str]:
    # A helper to get actively tracked symbols. For simplicity, we can fetch from meta_store.
    from backend.services.ingestion import ingestion_service
    # If ingestion_service isn't fully tracking it this way, we can also query the DB
    return ["EURUSD"] # Fallback or dynamic fetch

def eval_raja_sr_touch(rule: Dict[str, Any], state: Dict[str, Any]) -> Optional[str]:
    det = {"feature_id": "raja_sr_touch", "timeframe": rule.get("timeframe"), "params": {"limit": 400, "max_zones": 5}}
    rule2 = dict(rule)
    rule2["type"] = "detector_trigger"
    rule2["trigger_detectors"] = [det]
    return eval_detector_trigger(rule2, state)

def eval_msb_zigzag_break(rule: Dict[str, Any], state: Dict[str, Any]) -> Optional[str]:
    det = {
        "feature_id": "msb_zigzag_break",
        "timeframe": rule.get("timeframe"),
        "params": {"limit": 400, "detect_bos": bool(rule.get("detect_bos", True)), "detect_choch": bool(rule.get("detect_choch", True))},
    }
    rule2 = dict(rule)
    rule2["type"] = "detector_trigger"
    rule2["trigger_detectors"] = [det]
    return eval_detector_trigger(rule2, state)

def eval_trend_exhaustion(rule: Dict[str, Any], state: Dict[str, Any]) -> Optional[str]:
    det = {"feature_id": "trend_exhaustion", "timeframe": rule.get("timeframe"), "params": {"limit": 400}}
    rule2 = dict(rule)
    rule2["type"] = "detector_trigger"
    rule2["trigger_detectors"] = [det]
    return eval_detector_trigger(rule2, state)

def _mk_sig(parts: List[Any]) -> str:
    raw = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def eval_detector_trigger(rule: Dict[str, Any], state: Dict[str, Any]) -> Optional[str]:
    symbol = str(rule.get("symbol") or "").strip()
    default_tf = str(rule.get("timeframe") or "").strip()
    if not symbol or not default_tf:
        return None

    detectors = rule.get("trigger_detectors")
    if not isinstance(detectors, list) or not detectors:
        return None

    cooldown_minutes = _safe_int(rule.get("cooldown_minutes", 0))
    if cooldown_minutes > 0:
        last_ts = _safe_int(state.get("last_trigger_ts", 0))
        if last_ts > 0 and (int(time.time()) - last_ts) < cooldown_minutes * 60:
            return None

    try:
        from backend.domain.market.patterns.candles import detect_candlestick_patterns
        from backend.domain.market.patterns.breakouts import detect_false_breakout, detect_liquidity_sweep
        from backend.domain.market.patterns.pattern_detectors_v1 import (
            detect_bos_choch,
            detect_breakout_retest_hold,
            detect_close_outside_level_zone,
            detect_rectangle_ranges,
        )
        from backend.domain.market.structure.structures_tool_v1 import tool_structure_level_generator
        from backend.domain.market.indicators.ta import atr as _atr
    except Exception:
        return None

    def _bar_time_from_event(ev: Dict[str, Any]) -> Optional[int]:
        e = ev.get("evidence") if isinstance(ev.get("evidence"), dict) else {}
        if isinstance(e.get("bar_time"), int):
            return int(e.get("bar_time"))
        if isinstance(e.get("recover_time"), int):
            return int(e.get("recover_time"))
        if isinstance(e.get("confirm_time"), int):
            return int(e.get("confirm_time"))
        cont = e.get("continuation") if isinstance(e.get("continuation"), dict) else None
        if isinstance(cont, dict) and isinstance(cont.get("continue_time"), int):
            return int(cont.get("continue_time"))
        if isinstance(e.get("time"), int):
            return int(e.get("time"))
        if isinstance(e.get("to_time"), int):
            return int(e.get("to_time"))
        return None

    best_ev: Optional[Dict[str, Any]] = None
    best_time = -1
    best_score = -1.0

    cache_bars: Dict[str, List[Dict[str, Any]]] = {}
    cache_struct: Dict[str, Dict[str, Any]] = {}

    def _get_bars(tf: str, limit: int) -> List[Dict[str, Any]]:
        key = f"{tf}:{limit}"
        if key in cache_bars:
            return cache_bars[key]
        bars = historical_service.get_history(symbol, tf, before_time=0, limit=int(limit))
        cache_bars[key] = bars if isinstance(bars, list) else []
        return cache_bars[key]

    def _get_structures(tf: str, bars: List[Dict[str, Any]]) -> Dict[str, Any]:
        if tf in cache_struct:
            return cache_struct[tf]
        h4 = historical_service.get_history(symbol=symbol, timeframe="H4", limit=200)
        level_gen = {
            "sources": [
                {"type": "prev_day_high_low"},
                {"type": "fractal_levels", "timeframe": "H4", "pivot_left": 3, "pivot_right": 3},
            ],
            "output": {"max_levels": 8, "emit_zone": True, "zone_half_width_pips": {"default": {"pips": 15}}, "zone_max_age_bars": 300},
        }
        rep = tool_structure_level_generator({"bars_by_tf": {tf: bars, "H4": h4}, "primary_timeframe": tf, "level_generator": level_gen})
        levels = rep.get("levels") if isinstance(rep, dict) and isinstance(rep.get("levels"), list) else []
        zones = rep.get("zones") if isinstance(rep, dict) and isinstance(rep.get("zones"), list) else []
        cache_struct[tf] = {"levels": levels, "zones": zones}
        return cache_struct[tf]

    for d in detectors:
        if not isinstance(d, dict):
            continue
        fid = str(d.get("feature_id") or d.get("type") or "").strip()
        tf = str(d.get("timeframe") or default_tf).strip()
        prm = d.get("params") if isinstance(d.get("params"), dict) else {}
        if not fid or not tf:
            continue

        lb = 400
        if fid in ("rectangle_range", "false_breakout", "liquidity_sweep"):
            lb = _safe_int(prm.get("lookback_bars", 200), 200)
        if fid in ("close_outside_level_zone", "breakout_retest_hold"):
            lb = _safe_int(prm.get("lookback_bars", 300), 300)
        bars = _get_bars(tf, max(80, min(5000, lb)))
        if not bars or len(bars) < 10:
            continue

        events: List[Dict[str, Any]] = []
        if fid == "raja_sr_touch":
            lim = _safe_int(prm.get("limit", 400), 400)
            max_zones = _safe_int(prm.get("max_zones", 5), 5)
            bars = _get_bars(tf, max(80, min(5000, lim)))
            if not bars or len(bars) < 50:
                continue
            last_close = _safe_float((bars[-1] or {}).get("close"))
            zones = calc_raja_sr(bars, max_zones=int(max_zones))
            for z in zones if isinstance(zones, list) else []:
                if not isinstance(z, dict):
                    continue
                try:
                    if float(z.get("bottom")) <= float(last_close) <= float(z.get("top")):
                        ev = {
                            "id": "raja_sr_touch",
                            "type": "raja_sr_touch",
                            "direction": "Bearish" if str(z.get("type") or "").lower() == "resistance" else "Bullish",
                            "strength": "Medium",
                            "score": 75.0,
                            "evidence": {"zone_type": z.get("type"), "bottom": z.get("bottom"), "top": z.get("top"), "close": last_close, "bar_time": _safe_int((bars[-1] or {}).get("time"))},
                        }
                        ev["timeframe"] = tf
                        events.append(ev)
                        break
                except Exception:
                    continue

        elif fid == "msb_zigzag_break":
            lim = _safe_int(prm.get("limit", 400), 400)
            detect_bos = bool(prm.get("detect_bos", True))
            detect_choch = bool(prm.get("detect_choch", True))
            bars = _get_bars(tf, max(80, min(5000, lim)))
            if not bars or len(bars) < 50:
                continue
            last_t = _safe_int((bars[-1] or {}).get("time"))
            msb_res = calc_msb_zigzag(bars)
            lines = msb_res.get("lines") if isinstance(msb_res, dict) else None
            if not isinstance(lines, list) or not lines:
                continue
            latest_line = lines[-1]
            if not isinstance(latest_line, dict):
                continue
            if _safe_int(latest_line.get("time")) != last_t:
                continue
            ltype = str(latest_line.get("type") or "")
            is_bos = "BoS" in ltype
            is_choch = "ChoCh" in ltype
            if (is_bos and detect_bos) or (is_choch and detect_choch):
                ev = {
                    "id": "msb_zigzag_break",
                    "type": "msb_zigzag_break",
                    "direction": "Bullish" if ("Bull" in ltype) else "Bearish",
                    "strength": "Medium",
                    "score": 78.0,
                    "evidence": {"line_type": ltype, "level": latest_line.get("level"), "bar_time": last_t},
                    "timeframe": tf,
                }
                events.append(ev)

        elif fid == "trend_exhaustion":
            lim = _safe_int(prm.get("limit", 400), 400)
            bars = _get_bars(tf, max(80, min(5000, lim)))
            if not bars or len(bars) < 50:
                continue
            last_bar = bars[-1] or {}
            last_t = _safe_int(last_bar.get("time"))
            te = calc_trend_exhaustion(bars)
            ob_reversal = bool((te or {}).get("ob_reversal", False))
            os_reversal = bool((te or {}).get("os_reversal", False))
            if ob_reversal or os_reversal:
                ev = {
                    "id": "trend_exhaustion",
                    "type": "trend_exhaustion",
                    "direction": "Bearish" if ob_reversal else "Bullish",
                    "strength": "Medium",
                    "score": 78.0,
                    "evidence": {"bar_time": last_t, "close": _safe_float(last_bar.get("close")), "ob_reversal": ob_reversal, "os_reversal": os_reversal},
                    "timeframe": tf,
                }
                events.append(ev)

        elif fid == "candlestick":
            highs = [float(b["high"]) for b in bars if b.get("high") is not None]
            lows = [float(b["low"]) for b in bars if b.get("low") is not None]
            closes = [float(b["close"]) for b in bars if b.get("close") is not None]
            atr14 = _atr(highs, lows, closes, 14) or 0.0
            pats = detect_candlestick_patterns(
                bars,
                atr14=float(atr14 or 0.0),
                min_body_atr=float(prm.get("min_body_atr", 0.1)),
                min_range_atr=float(prm.get("min_range_atr", 0.15)),
                engulf_body_ratio=float(prm.get("engulf_body_ratio", 1.1)),
                doji_body_ratio=float(prm.get("doji_body_ratio", 0.1)),
                pin_wick_body_ratio=float(prm.get("pin_wick_body_ratio", 2.0)),
                pin_wick_range_ratio=float(prm.get("pin_wick_range_ratio", 0.55)),
            )
            for p in pats if isinstance(pats, list) else []:
                if isinstance(p, dict):
                    p2 = dict(p)
                    p2["type"] = "candlestick"
                    p2["timeframe"] = tf
                    events.append(p2)

        elif fid == "rectangle_range":
            rep = detect_rectangle_ranges(
                bars,
                lookback_bars=int(prm.get("lookback_bars", 120)),
                min_touches_per_side=int(prm.get("min_touches_per_side", 2)),
                tolerance_atr_mult=float(prm.get("tolerance_atr_mult", 0.25)),
                min_containment=float(prm.get("min_containment", 0.80)),
                max_height_atr=float(prm.get("max_height_atr", 8.0)),
                max_drift_atr=float(prm.get("max_drift_atr", 3.0)),
                max_efficiency=float(prm.get("max_efficiency", 0.45)),
                emit=str(prm.get("emit", "best") or "best"),
                max_results=int(prm.get("max_results", 50)),
                distinct_no_overlap=bool(prm.get("distinct_no_overlap", True)),
                dedup_iou=float(prm.get("dedup_iou", 0.55)),
            )
            items = rep.get("items") if isinstance(rep, dict) else None
            for it in items if isinstance(items, list) else []:
                if isinstance(it, dict):
                    it2 = dict(it)
                    it2["timeframe"] = tf
                    events.append(it2)

        elif fid == "bos_choch":
            got = detect_bos_choch(
                bars,
                lookback_bars=int(prm.get("lookback_bars", 220)),
                pivot_left=int(prm.get("pivot_left", 3)),
                pivot_right=int(prm.get("pivot_right", 3)),
                buffer=float(prm.get("buffer", 0.0)),
            )
            for it in got if isinstance(got, list) else []:
                if isinstance(it, dict):
                    it2 = dict(it)
                    it2["timeframe"] = tf
                    events.append(it2)

        elif fid in ("liquidity_sweep", "false_breakout", "close_outside_level_zone", "breakout_retest_hold"):
            st = _get_structures(tf, bars)
            levels = st.get("levels") if isinstance(st, dict) and isinstance(st.get("levels"), list) else []
            zones = st.get("zones") if isinstance(st, dict) and isinstance(st.get("zones"), list) else []

            if fid == "liquidity_sweep":
                got = detect_liquidity_sweep(
                    bars,
                    levels=levels,
                    lookback_bars=int(prm.get("lookback_bars", 160)),
                    buffer=float(prm.get("buffer", 0.0)),
                    buffer_atr_mult=float(prm.get("buffer_atr_mult", 0.05)),
                    recover_within_bars=int(prm.get("recover_within_bars", 3)),
                    max_candidates=int(prm.get("max_candidates", 40)),
                )
            elif fid == "false_breakout":
                got = detect_false_breakout(
                    bars,
                    levels=levels,
                    zones=zones,
                    lookback_bars=int(prm.get("lookback_bars", 120)),
                    buffer=float(prm.get("buffer", 0.0)),
                    buffer_atr_mult=float(prm.get("buffer_atr_mult", 0.05)),
                    max_candidates=int(prm.get("max_candidates", 30)),
                    include_raja_sr=bool(prm.get("include_raja_sr", True)),
                    max_raja_zones=int(prm.get("max_raja_zones", 6)),
                )
            elif fid == "close_outside_level_zone":
                got = detect_close_outside_level_zone(
                    bars,
                    levels=levels,
                    zones=zones,
                    close_buffer=float(prm.get("close_buffer", 0.0)),
                    scan_mode=str(prm.get("scan_mode", "realtime") or "realtime"),
                    lookback_bars=int(prm.get("lookback_bars", 300)),
                    confirm_mode=str(prm.get("confirm_mode", "one_body") or "one_body"),
                    confirm_n=int(prm.get("confirm_n", 2)),
                    max_events=min(50, int(prm.get("max_events", 20))),
                )
            else:
                got = detect_breakout_retest_hold(
                    bars,
                    levels=levels,
                    zones=zones,
                    scan_mode=str(prm.get("scan_mode", "realtime") or "realtime"),
                    lookback_bars=int(prm.get("lookback_bars", 300)),
                    confirm_mode=str(prm.get("confirm_mode", "one_body") or "one_body"),
                    confirm_n=int(prm.get("confirm_n", 2)),
                    retest_window_bars=int(prm.get("retest_window_bars", 16)),
                    continue_window_bars=int(prm.get("continue_window_bars", 8)),
                    buffer=float(prm.get("buffer", 0.0)),
                    pullback_margin=float(prm.get("pullback_margin", 0.0)),
                    max_events=min(50, int(prm.get("max_events", 20))),
                )
            for it in got if isinstance(got, list) else []:
                if isinstance(it, dict):
                    it2 = dict(it)
                    it2["timeframe"] = tf
                    events.append(it2)

        if not events:
            continue

        for ev in events:
            t = _bar_time_from_event(ev)
            score = _safe_float(ev.get("score", 0.0), 0.0)
            if t is None:
                continue
            if t > best_time or (t == best_time and score > best_score):
                best_time = int(t)
                best_score = float(score)
                best_ev = ev

    if best_ev is None:
        return None

    ev_time = _bar_time_from_event(best_ev) or 0
    ev_id = str(best_ev.get("id") or best_ev.get("type") or "event")
    ev_key = None
    ev_e = best_ev.get("evidence") if isinstance(best_ev.get("evidence"), dict) else {}
    if isinstance(ev_e.get("key"), str):
        ev_key = ev_e.get("key")
    sig = _mk_sig([symbol, ev_id, best_ev.get("timeframe"), ev_time, ev_key])
    if str(state.get("last_trigger_sig") or "") == sig:
        return None

    state["last_trigger_sig"] = sig
    state["last_triggered_bar_time"] = int(ev_time)
    state["last_trigger_ts"] = int(time.time())

    direction = str(best_ev.get("direction") or "")
    tf_out = str(best_ev.get("timeframe") or default_tf)
    msg = f"Detector Trigger: {symbol} ({tf_out}) {ev_id} {direction} score={_safe_float(best_ev.get('score'), 0.0):.1f}"
    return msg

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
    global _last_scan_log_ts
    now_ts = int(time.time())
    if now_ts - int(_last_scan_log_ts or 0) >= 60:
        _last_scan_log_ts = now_ts
        logger.info("alerts_scan enabled=%s", len(alerts))
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
        elif typ == "raja_sr_touch":
            msg = eval_raja_sr_touch(rule, state)
        elif typ == "msb_zigzag_break":
            msg = eval_msb_zigzag_break(rule, state)
        elif typ == "trend_exhaustion":
            msg = eval_trend_exhaustion(rule, state)
        elif typ == "detector_trigger":
            msg = eval_detector_trigger(rule, state)
        else:
            continue

        if msg:
            logger.info("alert_triggered alert_id=%s type=%s symbol=%s tf=%s", aid, typ, rule.get("symbol"), rule.get("timeframe"))
            append_event(aid, msg)
            logger.info("alert_event_saved alert_id=%s", aid)
            
            # If it's an AI Agent Trigger, spin up a background agent workflow!
            if typ in ["raja_sr_touch", "msb_zigzag_break", "trend_exhaustion", "detector_trigger"]:
                configs = rule.get("agent_configs", {})
                initial_prompt = configs.get("initial_prompt", f"Auto-triggered event: {msg}. Please analyze context and execute.")
                session_id = f"evt_{aid}_{uuid.uuid4().hex[:8]}"
                
                # telegram (optional)
                tg = rule.get("telegram") if isinstance(rule.get("telegram"), dict) else {}
                token = str(tg.get("token") or "")
                chat_id = str(tg.get("chat_id") or "")
                telegram_config = tg if token and chat_id else None
                
                try:
                    loop_obj = asyncio.get_running_loop()
                    logger.info("alert_workflow_schedule_start session=%s alert_id=%s", session_id, aid)
                    loop_obj.create_task(
                        AlertDualAgentWorkflow.run(
                            session_id=session_id,
                            initial_message=initial_prompt,
                            configs=configs,
                            symbol=rule.get("symbol", "XAUUSD"),
                            timeframe=rule.get("timeframe", "M15"),
                            alert_id=aid,
                            telegram_config=telegram_config,
                            trigger_type=typ,
                            trigger_text=msg,
                        )
                    )
                    logger.info("alert_workflow_scheduled session=%s alert_id=%s", session_id, aid)
                except Exception:
                    logger.exception("alert_workflow_schedule_failed alert_id=%s", aid)

            # send initial telegram alert right away if configured
            tg = rule.get("telegram") if isinstance(rule.get("telegram"), dict) else {}
            token = str(tg.get("token") or "")
            chat_id = str(tg.get("chat_id") or "")
            if token and chat_id:
                try:
                    asyncio.get_running_loop().create_task(
                        asyncio.to_thread(send_telegram_message, bot_token=token, chat_id=chat_id, text=msg)
                    )
                except Exception:
                    logger.exception("alert_initial_telegram_failed alert_id=%s", aid)
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
            logger.exception("alerts_engine_eval_failed")
        await asyncio.sleep(interval_sec)
