import copy
import time
from collections import OrderedDict
from threading import Lock

import json
from typing import Any, Dict, List

from backend.services.ai.agent_context_builder import build_agent_context
from backend.domain.market.structure.msb import calc_msb_zigzag
from backend.domain.market.structure.raja_sr_calc import calc_raja_sr
from backend.services.historical import historical_service

_CACHE_LOCK = Lock()
_EVENT_CONTEXT_CACHE: "OrderedDict[tuple, tuple[float, dict]]" = OrderedDict()
_EVENT_CONTEXT_CACHE_MAX = 32
_EVENT_CONTEXT_CACHE_TTL_SEC = 60


def _build_event_context_uncached(
    *,
    event_id: str,
    trigger_type: str,
    trigger_text: str,
    trigger_payload: Dict[str, Any] | None,
    symbol: str,
    event_timeframe: str,
    history_limits: Dict[str, int] | None = None,
    configs: dict | None = None,
) -> Dict[str, Any]:
    compute_limits = history_limits or {"H1": 400, "M15": 600, "H4": 200}
    ohlcv_payload_limits = {"H1": 25, "M15": 50, "H4": 15}
    snapshot_time = None
    missing: List[str] = []
    market: Dict[str, Any] = {"ohlcv": {}, "indicators": {}}
    now_ts = int(__import__("time").time())
    import hashlib as _hashlib

    def _ts_to_iso(ts: int | None) -> str | None:
        if ts is None:
            return None
        try:
            import datetime as dt

            return dt.datetime.fromtimestamp(int(ts), tz=dt.timezone.utc).isoformat().replace("+00:00", "Z")
        except Exception:
            return None

    def _session_type_utc(ts: int | None) -> str | None:
        if ts is None:
            return None
        try:
            import datetime as dt

            d = dt.datetime.fromtimestamp(int(ts), tz=dt.timezone.utc)
            h = int(d.hour)
            dow = int(d.weekday())  # Mon=0..Sun=6
            if h >= 21:
                return "SYDNEY" if dow == 0 else "ASIA"
            if 0 <= h < 7:
                return "ASIA"
            if 7 <= h < 12:
                return "EUROPE"
            if 12 <= h < 21:
                return "US"
            return "ASIA"
        except Exception:
            return None

    def _market_session_utc(ts: int | None) -> str | None:
        if ts is None:
            return None
        try:
            import datetime as dt

            d = dt.datetime.fromtimestamp(int(ts), tz=dt.timezone.utc)
            h = int(d.hour)
            if 0 <= h < 7:
                return "Asia"
            if 7 <= h < 12:
                return "London_AM"
            if 12 <= h < 16:
                return "London-NY Overlap"
            if 16 <= h < 21:
                return "NY_PM"
            return "Asia"
        except Exception:
            return None

    def _get_quote(symbol_: str, fallback_last: float | None) -> dict:
        try:
            from backend.data_sources.mt5_source import MT5_AVAILABLE
        except Exception:
            MT5_AVAILABLE = False
        if not MT5_AVAILABLE:
            return {
                "ok": True,
                "symbol": symbol_,
                "bid": None,
                "ask": None,
                "last": fallback_last,
                "spread": None,
                "time": None,
                "source": "history_close",
            }
        try:
            import MetaTrader5 as mt5  # type: ignore

            tick = mt5.symbol_info_tick(symbol_)
            if tick is None:
                return {"ok": False, "error": "symbol_info_tick returned None"}
            bid = float(getattr(tick, "bid", 0.0) or 0.0)
            ask = float(getattr(tick, "ask", 0.0) or 0.0)
            last = float(getattr(tick, "last", 0.0) or 0.0) or (bid if bid else fallback_last)
            spread = (ask - bid) if (ask and bid) else None
            t = int(getattr(tick, "time", 0) or 0) or None
            return {
                "ok": True,
                "symbol": symbol_,
                "bid": bid or None,
                "ask": ask or None,
                "last": last,
                "spread": spread,
                "time": t,
                "source": "mt5_tick",
            }
        except Exception as e:
            return {"ok": False, "error": f"mt5_quote_failed: {e}"}

    def _infer_vol_regime(bars: list[dict], window: int = 20) -> str:
        if not bars or len(bars) < window * 2:
            return "unknown"
        try:
            def _avg_rng(xs: list[dict]) -> float:
                s = 0.0
                n = 0
                for b in xs:
                    hi = b.get("high")
                    lo = b.get("low")
                    if hi is None or lo is None:
                        continue
                    s += float(hi) - float(lo)
                    n += 1
                return s / max(1, n)

            recent = _avg_rng(bars[-window:])
            prev = _avg_rng(bars[-window * 2 : -window])
            if prev <= 0:
                return "unknown"
            r = recent / prev
            if r >= 1.2:
                return "expanding"
            if r <= 0.8:
                return "contracting"
            return "normal"
        except Exception:
            return "unknown"

    def _round3_any(x: Any) -> Any:
        if isinstance(x, bool) or x is None:
            return x
        if isinstance(x, int):
            return x
        if isinstance(x, float):
            return round(x, 3)
        if isinstance(x, dict):
            return {k: _round3_any(v) for k, v in x.items()}
        if isinstance(x, list):
            return [_round3_any(v) for v in x]
        return x

    def _mk_evidence_id(prefix: str, parts: list[Any]) -> str:
        raw = "|".join("" if p is None else str(p) for p in parts)
        h = _hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
        return f"{prefix}_{h}"

    def build_for_tf(tf: str, *, include_indicators: bool) -> None:
        nonlocal snapshot_time
        bars_full = historical_service.get_history(symbol=symbol, timeframe=tf, limit=int(compute_limits.get(tf, 500)))
        if not bars_full:
            missing.append(f"ohlcv:{tf}")
            market["ohlcv"][tf] = []
            if include_indicators:
                market["indicators"][tf] = {"error": "no_data"}
            return
        try:
            from bisect import bisect_right

            times_full = [int(b.get("time")) for b in bars_full if b.get("time") is not None]
            time_to_idx = {t: i for i, t in enumerate(times_full)}

            def _age_candles(ts: int | None) -> int | None:
                if ts is None or not times_full:
                    return None
                try:
                    t = int(ts)
                except Exception:
                    return None
                idx = time_to_idx.get(t)
                if idx is None:
                    pos = bisect_right(times_full, t) - 1
                    if pos < 0:
                        return None
                    idx = pos
                return int((len(times_full) - 1) - idx)

        except Exception:
            def _age_candles(ts: int | None) -> int | None:
                return None

        n_payload = int(ohlcv_payload_limits.get(tf, 0) or 0)
        bars_payload = bars_full[-n_payload:] if n_payload > 0 else list(bars_full)

        has_nonzero_dv = False
        for b in bars_payload:
            dv = b.get("delta_volume")
            try:
                if dv is not None and float(dv) != 0.0:
                    has_nonzero_dv = True
                    break
            except Exception:
                continue

        if has_nonzero_dv:
            market["ohlcv"][tf] = [
                {
                    "time_iso": _ts_to_iso(b.get("time")),
                    "bars_ago": int((len(bars_payload) - 1) - i),
                    "open": b.get("open"),
                    "high": b.get("high"),
                    "low": b.get("low"),
                    "close": b.get("close"),
                    "tick_volume": b.get("tick_volume"),
                    "delta_volume": b.get("delta_volume"),
                }
                for i, b in enumerate(bars_payload)
            ]
        else:
            market["ohlcv"][tf] = [
                {
                    "time_iso": _ts_to_iso(b.get("time")),
                    "bars_ago": int((len(bars_payload) - 1) - i),
                    "open": b.get("open"),
                    "high": b.get("high"),
                    "low": b.get("low"),
                    "close": b.get("close"),
                    "tick_volume": b.get("tick_volume"),
                }
                for i, b in enumerate(bars_payload)
            ]

        if not include_indicators:
            if snapshot_time is None and bars_full:
                snapshot_time = bars_full[-1].get("time")
            return

        try:
            context = json.loads(build_agent_context(bars_full))
        except Exception:
            missing.append(f"context_parse:{tf}")
            market["indicators"][tf] = {"error": "context_parse_failed"}
            return

        try:
            zones_all = calc_raja_sr(bars_full)
        except Exception:
            zones_all = None
            missing.append(f"raja_sr_zones:{tf}")

        try:
            msb = calc_msb_zigzag(bars_full)
        except Exception:
            msb = None
            missing.append(f"msb_zigzag:{tf}")

        current_price = context.get("current_price")
        try:
            p = float(current_price) if current_price is not None else None
        except Exception:
            p = None

        active_zones: list[dict] = []
        if isinstance(zones_all, list) and p is not None:
            above: list[tuple[float, dict]] = []
            below: list[tuple[float, dict]] = []
            for z in zones_all:
                try:
                    bottom = float(z.get("bottom"))
                    top = float(z.get("top"))
                except Exception:
                    continue
                mid = (bottom + top) / 2.0
                dist = mid - p
                lt = z.get("last_touch_time")
                bottom_r = round(bottom, 3)
                top_r = round(top, 3)
                item = {
                    "evidence_id": _mk_evidence_id(
                        f"zone_{tf}",
                        [z.get("type"), bottom_r, top_r, z.get("touches"), _ts_to_iso(lt)],
                    ),
                    "type": z.get("type"),
                    "level_zone_bottom_edge_price": bottom,
                    "level_zone_top_edge_price": top,
                    "score": z.get("score"),
                    "touches": z.get("touches"),
                    "last_touch_time_iso": _ts_to_iso(lt),
                    "last_touch_age_candles": _age_candles(lt),
                    "distance_to_price_points": float(abs(dist)),
                    "distance_pct": float(abs(dist) / p) if p else None,
                }
                zt = str(item.get("type") or "").lower()
                if bottom <= p <= top:
                    if zt == "resistance":
                        above.append((0.0, item))
                    else:
                        below.append((0.0, item))
                    continue
                if zt == "resistance":
                    if mid >= p:
                        above.append((abs(dist), item))
                    continue
                if zt == "support":
                    if mid <= p:
                        below.append((abs(dist), item))
                    continue
                if mid >= p:
                    above.append((abs(dist), item))
                else:
                    below.append((abs(dist), item))
            above_sorted = [x[1] for x in sorted(above, key=lambda t: t[0])][:3]
            below_sorted = [x[1] for x in sorted(below, key=lambda t: t[0])][:3]
            active_zones = above_sorted + below_sorted

        if str(trigger_type or "") == "raja_sr_touch" and isinstance(trigger_payload, dict):
            be = trigger_payload.get("best_event")
            ev = be if isinstance(be, dict) else None
            e = (ev or {}).get("evidence") if isinstance((ev or {}).get("evidence"), dict) else None
            zone_id = str((e or {}).get("zone_id") or "")
            if zone_id and str((ev or {}).get("timeframe") or "") == tf:
                found = False
                for it in active_zones:
                    if isinstance(it, dict) and str(it.get("evidence_id") or "") == zone_id:
                        it["is_trigger_zone"] = True
                        found = True
                        break
                if not found:
                    try:
                        bottom = float((e or {}).get("bottom"))
                        top = float((e or {}).get("top"))
                    except Exception:
                        bottom = None
                        top = None
                    if bottom is not None and top is not None and bottom > 0 and top > 0:
                        mid = (bottom + top) / 2.0
                        dist = float(abs(mid - p)) if p is not None else None
                        item = {
                            "evidence_id": zone_id,
                            "type": (e or {}).get("zone_type"),
                            "level_zone_bottom_edge_price": bottom,
                            "level_zone_top_edge_price": top,
                            "score": (e or {}).get("score"),
                            "touches": (e or {}).get("touches"),
                            "last_touch_time_iso": (e or {}).get("last_touch_time_iso"),
                            "last_touch_age_candles": (e or {}).get("age_candles"),
                            "distance_to_price_points": dist,
                            "distance_pct": float(abs(mid - p) / p) if p else None,
                            "is_trigger_zone": True,
                        }
                        active_zones = [item] + active_zones

        recent_breaks: list[dict] = []
        if isinstance(msb, dict):
            lines = msb.get("lines")
            if isinstance(lines, list) and lines:
                tail = lines[-5:]
                for it in tail:
                    if not isinstance(it, dict):
                        continue
                    try:
                        lvl = float(it.get("level"))
                    except Exception:
                        lvl = None
                    dist_pts = float(abs(lvl - p)) if (lvl is not None and p is not None) else None
                    t = it.get("time")
                    lvl_r = round(lvl, 3) if isinstance(lvl, float) else lvl
                    t_iso = _ts_to_iso(t)
                    recent_breaks.append(
                        {
                            "evidence_id": _mk_evidence_id(f"break_{tf}", [it.get("type"), lvl_r, t_iso]),
                            "type": it.get("type"),
                            "level_price": lvl,
                            "time_iso": t_iso,
                            "age_candles": _age_candles(t),
                            "distance_to_price_points": dist_pts,
                        }
                    )

        adv = context.get("advanced_indicators") or {}
        if isinstance(adv, dict):
            adv = {k: v for k, v in adv.items() if k not in ("Nearest_Resistance", "Nearest_Support", "Recent_Structure_Breaks")}

        market["indicators"][tf] = {
            "current_price": current_price,
            "basic_indicators": context.get("basic_indicators"),
            "advanced_indicators": adv,
            "active_zones": active_zones,
            "recent_structure_breaks": recent_breaks,
        }

        if snapshot_time is None and bars_full:
            snapshot_time = bars_full[-1].get("time")

    build_for_tf("H4", include_indicators=False)
    build_for_tf("H1", include_indicators=True)
    build_for_tf("M15", include_indicators=True)
    if event_timeframe not in ("H1", "M15", "H4"):
        build_for_tf(event_timeframe, include_indicators=True)

    trend_tf = "H1"
    exec_tf = "M15"
    liquiditylevel_tf = "H4"
    direction = "neutral"
    consistency = "unknown"
    note = ""
    try:
        h1_adv = (market.get("indicators") or {}).get(trend_tf, {}).get("advanced_indicators") or {}
        m15_adv = (market.get("indicators") or {}).get(exec_tf, {}).get("advanced_indicators") or {}
        h1_struct = str(h1_adv.get("Market_Structure") or "")
        m15_struct = str(m15_adv.get("Market_Structure") or "")
        if h1_struct == "HH_HL":
            direction = "bullish"
        elif h1_struct == "LH_LL":
            direction = "bearish"
        else:
            direction = "neutral"
        if not m15_struct:
            consistency = "unknown"
        elif m15_struct == h1_struct:
            consistency = "high"
        elif m15_struct == "Consolidation":
            consistency = "moderate"
        else:
            consistency = "low"
        note = f"{trend_tf}={h1_struct or 'n/a'}, {exec_tf}={m15_struct or 'n/a'}"
    except Exception:
        pass

    current_session = _session_type_utc(snapshot_time)
    market_session = _market_session_utc(snapshot_time)
    quote = _get_quote(symbol, fallback_last=None)
    fallback_last = None
    try:
        last_bar = (market.get("ohlcv") or {}).get(exec_tf, [])[-1]
        fallback_last = float(last_bar.get("close")) if last_bar and last_bar.get("close") is not None else None
    except Exception:
        fallback_last = None
    if quote.get("ok") and quote.get("last") is None:
        quote["last"] = fallback_last
    if isinstance(quote, dict):
        quote["time_iso"] = _ts_to_iso(quote.get("time"))
        quote.pop("time", None)

    exec_full = historical_service.get_history(symbol=symbol, timeframe=exec_tf, limit=int(compute_limits.get(exec_tf, 600)))
    market.setdefault("patterns", {})
    market.setdefault("pattern_events", {})
    market.setdefault("structures", {})
    computed_features: List[str] = []
    feature_cfg = None
    try:
        if isinstance(configs, dict):
            feature_cfg = configs.get("context_features")
    except Exception:
        feature_cfg = None
    enabled_features: set[str] | None = None
    feature_params: dict = {}
    feature_tf = exec_tf
    if isinstance(feature_cfg, dict):
        en = feature_cfg.get("enabled")
        if isinstance(en, list) and any(isinstance(x, str) and x for x in en):
            enabled_features = set(str(x) for x in en if isinstance(x, str) and x)
        p = feature_cfg.get("params")
        if isinstance(p, dict):
            feature_params = p
        try:
            tf_v = feature_cfg.get("timeframe")
            if isinstance(tf_v, str) and tf_v:
                feature_tf = tf_v
        except Exception:
            feature_tf = exec_tf

    bars_for_features = exec_full
    if feature_tf != exec_tf:
        try:
            bars_for_features = historical_service.get_history(symbol=symbol, timeframe=feature_tf, limit=int(compute_limits.get(feature_tf, compute_limits.get(exec_tf, 600))))
        except Exception:
            bars_for_features = exec_full

    def _feature_enabled(fid: str) -> bool:
        if enabled_features is None:
            return True
        return fid in enabled_features

    def _params_for(fid: str) -> dict:
        v = feature_params.get(fid)
        return v if isinstance(v, dict) else {}
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
    except Exception:
        detect_candlestick_patterns = None
        detect_rectangle_ranges = None
        detect_bos_choch = None
        detect_liquidity_sweep = None
        detect_false_breakout = None
        detect_close_outside_level_zone = None
        detect_breakout_retest_hold = None
        tool_structure_level_generator = None

    if bars_for_features and _feature_enabled("candlestick") and isinstance(detect_candlestick_patterns, object) and detect_candlestick_patterns:
        try:
            highs = [float(b["high"]) for b in bars_for_features if b.get("high") is not None]
            lows = [float(b["low"]) for b in bars_for_features if b.get("low") is not None]
            closes = [float(b["close"]) for b in bars_for_features if b.get("close") is not None]
            atr14 = None
            try:
                from backend.domain.market.indicators.ta import atr as _atr

                atr14 = _atr(highs, lows, closes, 14)
            except Exception:
                atr14 = None
            prm = _params_for("candlestick")
            pats = detect_candlestick_patterns(
                bars_for_features,
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
                    p["timeframe"] = feature_tf
            market["patterns"][feature_tf] = market.get("patterns", {}).get(feature_tf, {})
            if isinstance(market["patterns"][feature_tf], dict):
                market["patterns"][feature_tf]["candlestick"] = pats if isinstance(pats, list) else []
            computed_features.append("candlestick")
        except Exception:
            missing.append(f"patterns:candlestick:{feature_tf}")

    if bars_for_features and _feature_enabled("rectangle_range") and isinstance(detect_rectangle_ranges, object) and detect_rectangle_ranges:
        try:
            prm = _params_for("rectangle_range")
            rep = detect_rectangle_ranges(
                bars_for_features,
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
            rects = items if isinstance(items, list) else []
            curr_p = None
            try:
                q = quote if isinstance(quote, dict) else {}
                curr_p = float(q.get("last")) if q and q.get("last") is not None else None
            except Exception:
                curr_p = None
            if curr_p is None:
                try:
                    last_bar = bars_for_features[-1] if isinstance(bars_for_features, list) and bars_for_features else None
                    curr_p = float((last_bar or {}).get("close")) if isinstance(last_bar, dict) and (last_bar or {}).get("close") is not None else None
                except Exception:
                    curr_p = None
            for it in rects:
                if isinstance(it, dict):
                    it["timeframe"] = feature_tf
                    try:
                        top = float(it.get("top"))
                        bottom = float(it.get("bottom"))
                    except Exception:
                        top = None
                        bottom = None
                    top_r = round(top, 3) if isinstance(top, float) else top
                    bottom_r = round(bottom, 3) if isinstance(bottom, float) else bottom
                    raw = "|".join(
                        str(x)
                        for x in [
                            int(it.get("from_time") or 0),
                            int(it.get("to_time") or 0),
                            top_r,
                            bottom_r,
                            int(it.get("touches_top") or 0),
                            int(it.get("touches_bottom") or 0),
                        ]
                    )
                    it["rect_id"] = f"rect_{feature_tf}_{_hashlib.sha1(raw.encode('utf-8')).hexdigest()[:10]}"
                    if top is not None and bottom is not None and curr_p is not None:
                        it["is_price_inside"] = bool(bottom <= curr_p <= top)
                        it["distance_to_price_points"] = 0.0 if (bottom <= curr_p <= top) else float(abs(((bottom + top) / 2.0) - curr_p))
                    if isinstance(trigger_payload, dict):
                        be = trigger_payload.get("best_event")
                        ev = be if isinstance(be, dict) else None
                        if isinstance(ev, dict) and str(ev.get("type") or "") == "consolidation_rectangle_breakout":
                            e = ev.get("evidence") if isinstance(ev.get("evidence"), dict) else None
                            if isinstance(e, dict) and str(e.get("rect_id") or "") == str(it.get("rect_id") or ""):
                                it["is_trigger_rectangle"] = True
            market["patterns"][feature_tf] = market.get("patterns", {}).get(feature_tf, {})
            if isinstance(market["patterns"][feature_tf], dict):
                market["patterns"][feature_tf]["rectangle_ranges"] = rects
                if isinstance(rep, dict) and isinstance(rep.get("candidates"), int):
                    market["patterns"][feature_tf]["rectangle_candidates_total"] = int(rep["candidates"])
            computed_features.append("rectangle_range")
        except Exception:
            missing.append(f"patterns:rectangle_range:{feature_tf}")

    levels: List[Dict[str, Any]] = []
    zones: List[Dict[str, Any]] = []
    need_structures = _feature_enabled("structures_levels_zones") or any(
        _feature_enabled(x) for x in ("liquidity_sweep", "false_breakout", "close_outside_level_zone", "breakout_retest_hold")
    )
    if bars_for_features and need_structures and isinstance(tool_structure_level_generator, object) and tool_structure_level_generator:
        try:
            h4_full = historical_service.get_history(symbol=symbol, timeframe=liquiditylevel_tf, limit=int(compute_limits.get(liquiditylevel_tf, 200)))
            level_gen = {
                "sources": [
                    {"type": "prev_day_high_low"},
                    {"type": "fractal_levels", "timeframe": liquiditylevel_tf, "pivot_left": 3, "pivot_right": 3},
                ],
                "output": {
                    "max_levels": 8,
                    "emit_zone": True,
                    "zone_half_width_pips": {"default": {"pips": 15}},
                    "zone_max_age_bars": 300,
                },
            }
            rep = tool_structure_level_generator({"bars_by_tf": {feature_tf: bars_for_features, liquiditylevel_tf: h4_full}, "primary_timeframe": feature_tf, "level_generator": level_gen})
            levels = rep.get("levels") if isinstance(rep, dict) and isinstance(rep.get("levels"), list) else []
            zones = rep.get("zones") if isinstance(rep, dict) and isinstance(rep.get("zones"), list) else []
            brief_levels = []
            for lv in levels[:12]:
                if not isinstance(lv, dict):
                    continue
                brief_levels.append({"price": lv.get("price"), "kind": lv.get("kind"), "time": lv.get("time")})
            brief_zones = []
            for z in zones[:12]:
                if not isinstance(z, dict):
                    continue
                brief_zones.append(
                    {
                        "top": z.get("top"),
                        "bottom": z.get("bottom"),
                        "from_time": z.get("from_time"),
                        "to_time": z.get("to_time"),
                        "kind": (z.get("source_level") or {}).get("kind") if isinstance(z.get("source_level"), dict) else z.get("kind"),
                        "center": z.get("center"),
                    }
                )
            market["structures"][feature_tf] = {"levels": brief_levels, "zones": brief_zones}
            computed_features.append("structures.levels_zones")
        except Exception:
            missing.append(f"structures:levels_zones:{feature_tf}")

    ev_items: List[Dict[str, Any]] = []
    if bars_for_features and _feature_enabled("bos_choch") and isinstance(detect_bos_choch, object) and detect_bos_choch:
        try:
            prm = _params_for("bos_choch")
            got = detect_bos_choch(
                bars_for_features,
                lookback_bars=int(prm.get("lookback_bars", 220)),
                pivot_left=int(prm.get("pivot_left", 3)),
                pivot_right=int(prm.get("pivot_right", 3)),
                buffer=float(prm.get("buffer", 0.0)),
            )
            for it in got if isinstance(got, list) else []:
                if isinstance(it, dict):
                    it["timeframe"] = feature_tf
                    ev_items.append(it)
            computed_features.append("bos_choch")
        except Exception:
            missing.append(f"events:bos_choch:{feature_tf}")

    if bars_for_features and levels and _feature_enabled("liquidity_sweep") and isinstance(detect_liquidity_sweep, object) and detect_liquidity_sweep:
        try:
            prm = _params_for("liquidity_sweep")
            got = detect_liquidity_sweep(
                bars_for_features,
                levels=levels,
                lookback_bars=int(prm.get("lookback_bars", 160)),
                buffer=float(prm.get("buffer", 0.0)),
                buffer_atr_mult=float(prm.get("buffer_atr_mult", 0.05)),
                recover_within_bars=int(prm.get("recover_within_bars", 3)),
                max_candidates=int(prm.get("max_candidates", 40)),
            )
            for it in got if isinstance(got, list) else []:
                if isinstance(it, dict):
                    it["timeframe"] = feature_tf
                    ev_items.append(it)
            computed_features.append("liquidity_sweep")
        except Exception:
            missing.append(f"events:liquidity_sweep:{feature_tf}")

    if bars_for_features and _feature_enabled("false_breakout") and isinstance(detect_false_breakout, object) and detect_false_breakout:
        try:
            prm = _params_for("false_breakout")
            got = detect_false_breakout(
                bars_for_features,
                levels=levels,
                zones=zones,
                lookback_bars=int(prm.get("lookback_bars", 120)),
                buffer=float(prm.get("buffer", 0.0)),
                buffer_atr_mult=float(prm.get("buffer_atr_mult", 0.05)),
                max_candidates=int(prm.get("max_candidates", 30)),
                include_raja_sr=bool(prm.get("include_raja_sr", True)),
                max_raja_zones=int(prm.get("max_raja_zones", 6)),
            )
            for it in got if isinstance(got, list) else []:
                if isinstance(it, dict):
                    it["timeframe"] = feature_tf
                    ev_items.append(it)
            computed_features.append("false_breakout")
        except Exception:
            missing.append(f"events:false_breakout:{feature_tf}")

    if bars_for_features and zones and _feature_enabled("close_outside_level_zone") and isinstance(detect_close_outside_level_zone, object) and detect_close_outside_level_zone:
        try:
            prm = _params_for("close_outside_level_zone")
            got = detect_close_outside_level_zone(
                bars_for_features,
                levels=levels,
                zones=zones,
                close_buffer=float(prm.get("close_buffer", 0.0)),
                scan_mode=str(prm.get("scan_mode", "realtime") or "realtime"),
                lookback_bars=int(prm.get("lookback_bars", 300)),
                confirm_mode=str(prm.get("confirm_mode", "one_body") or "one_body"),
                confirm_n=int(prm.get("confirm_n", 2)),
                max_events=min(50, int(prm.get("max_events", 20))),
            )
            for it in got if isinstance(got, list) else []:
                if isinstance(it, dict):
                    it["timeframe"] = feature_tf
                    ev_items.append(it)
            computed_features.append("close_outside_level_zone")
        except Exception:
            missing.append(f"events:close_outside_level_zone:{feature_tf}")

    if bars_for_features and zones and _feature_enabled("breakout_retest_hold") and isinstance(detect_breakout_retest_hold, object) and detect_breakout_retest_hold:
        try:
            prm = _params_for("breakout_retest_hold")
            got = detect_breakout_retest_hold(
                bars_for_features,
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
                    it["timeframe"] = feature_tf
                    ev_items.append(it)
            computed_features.append("breakout_retest_hold")
        except Exception:
            missing.append(f"events:breakout_retest_hold:{feature_tf}")

    if ev_items:
        market["pattern_events"][feature_tf] = ev_items[:40]
    if computed_features:
        market["computed_features"] = computed_features
    vol_regime = _infer_vol_regime(exec_full)
    volume_activity = "unknown"
    try:
        if exec_full and len(exec_full) >= 30:
            vols = [float(b.get("tick_volume") or 0.0) for b in exec_full]
            recent = sum(vols[-10:]) / 10.0
            base = sorted(vols[-30:-10])[len(vols[-30:-10]) // 2] if len(vols[-30:-10]) >= 1 else 0.0
            if base > 0 and recent >= base * 1.5:
                volume_activity = "spike"
            elif base > 0 and recent <= base * 0.7:
                volume_activity = "dull"
            else:
                volume_activity = "normal"
    except Exception:
        volume_activity = "unknown"

    upcoming_news_impact = "unknown"
    try:
        import os
        import json as _json

        cal_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "calendar.json")
        if os.path.exists(cal_path):
            with open(cal_path, "r", encoding="utf-8") as f:
                cal = _json.load(f) or {}
            events = cal.get("events") if isinstance(cal, dict) else None
            if isinstance(events, list):
                horizon = now_ts + 2 * 3600
                best = "none"
                rank = {"High": 3, "Medium": 2, "Low": 1}
                best_r = 0
                for ev in events:
                    if not isinstance(ev, dict):
                        continue
                    t = ev.get("timestamp")
                    if t is None:
                        continue
                    try:
                        t = int(t)
                    except Exception:
                        continue
                    if not (now_ts <= t <= horizon):
                        continue
                    imp = str(ev.get("impact") or "")
                    r = rank.get(imp, 0)
                    if r > best_r:
                        best_r = r
                        best = imp
                if best == "none":
                    upcoming_news_impact = "none"
                elif best == "High":
                    upcoming_news_impact = "high"
                elif best == "Medium":
                    upcoming_news_impact = "medium"
                elif best == "Low":
                    upcoming_news_impact = "low"
    except Exception:
        upcoming_news_impact = "unknown"

    session_vp = {}
    try:
        from backend.services.chart_scene.session_vp import SessionVPOptions, calculate_all

        data = []
        for b in exec_full:
            if not isinstance(b, dict):
                continue
            data.append(
                {
                    "time": b.get("time"),
                    "open": b.get("open"),
                    "high": b.get("high"),
                    "low": b.get("low"),
                    "close": b.get("close"),
                    "volume": b.get("tick_volume") or b.get("volume") or 0,
                }
            )
        blocks = calculate_all(data, SessionVPOptions(days_to_calculate=5, bins=70, value_area_pct=70.0))
        if blocks:
            cur = blocks[-1]
            prev = blocks[-2] if len(blocks) >= 2 else None

            def _brief(blk: dict | None) -> dict | None:
                if not blk:
                    return None
                return {
                    "id": blk.get("id"),
                    "type": blk.get("type"),
                    "firstBarTimeIso": _ts_to_iso(blk.get("firstBarTime")),
                    "lastBarTimeIso": _ts_to_iso(blk.get("lastBarTime")),
                    "pocPrice": blk.get("pocPrice"),
                    "valueAreaLow": blk.get("valueAreaLow"),
                    "valueAreaHigh": blk.get("valueAreaHigh"),
                }

            session_vp = {"current": _brief(cur), "previous": _brief(prev)}
    except Exception:
        session_vp = {}

    indicator_notes = {
        "SMA_20": "简单移动平均线(20)，单位为价格点。",
        "SMA_50": "简单移动平均线(50)，单位为价格点。",
        "EMA_20": "指数移动平均线(20)，单位为价格点。",
        "ATR_14": "真实波幅均值(14)，单位为价格点（常用于止损距离参考）。",
        "RSI_14": "相对强弱指数(14)，范围 0-100。",
        "MACD": "MACD(12,26,9)：macd/signal/hist 单位为价格点。",
        "VolumeProfile_POC": "Volume Profile 的 POC 价格（成交量最大价位），单位为价格点。",
        "VolumeProfile_VAL": "Value Area Low（70%价值区下沿），单位为价格点。",
        "VolumeProfile_VAH": "Value Area High（70%价值区上沿），单位为价格点。",
        "Trend_Exhaustion": "趋势衰竭状态（超买/超卖与反转标记）。",
        "Market_Structure": "结构状态：HH_HL / LH_LL / Consolidation。",
        "Structure_High": "确认结构高点（用于结构突破/失效判断）。",
        "Structure_Low": "确认结构低点（用于结构突破/失效判断）。",
        "active_zones": "基于 RajaSR 的上下临近支撑/阻力区间（上3+下3），含距离字段。",
        "recent_structure_breaks": "最近结构事件（BoS/ChoCh）子集（最近5条），含距离字段。",
        "patterns.candlestick": "蜡烛形态事件列表（doji/inside_bar/engulfing/pinbar 等），用于补强入场/失效判断（可选字段）。",
        "patterns.rectangle_ranges": "箱体/区间识别结果列表（range top/bottom + touches/效率等），用于判断震荡与突破/回踩（可选字段）。",
        "patterns.rectangle_candidates_total": "本次 rectangle_range 扫描到的候选区间总数（调参/诊断用）。",
        "structures.levels": "结构关键价位列表（由 prev_day/fractal 等来源生成），用于 BOS/假突破/回踩等检测（可选字段）。",
        "structures.zones": "结构关键区域列表（围绕 levels 生成的 zone：top/bottom/half_width），用于 close_outside/breakout_retest 等检测（可选字段）。",
        "pattern_events": "结构/突破类事件列表（如 bos_choch/liquidity_sweep/false_breakout/close_outside/breakout_retest_hold 等），优先引用 evidence.bar_time 与关键价位字段（可选字段）。",
        "bos_choch": "BOS/CHOCH 事件（突破/换向），用于趋势确认与失效判断（可选字段）。",
        "liquidity_sweep": "扫流动性事件：刺破关键位后快速回收（recover_within_bars），常用于反转/失败突破（可选字段）。",
        "false_breakout": "假突破事件：突破区间/关键位但收盘回到区间内，优先关注 close 相对 zone 的位置（可选字段）。",
        "close_outside_level_zone": "收盘实体确认出界：M15 实体收盘在 level zone 外侧，用于有效突破/跌破判定（可选字段）。",
        "breakout_retest_hold": "突破→回踩→延续（hold）结构链路事件，用于顺势入场与回踩有效性（可选字段）。",
        "volume_activity": "成交量活动：spike/dull/normal（基于近期 M15 tick_volume 相对强弱）。",
        "vol_regime": "波动环境：expanding/contracting/normal（基于近期区间振幅相对变化）。",
        "session_vp": "Session Volume Profile：当前与前一 session 的 POC/VAH/VAL 摘要。",
    }

    trigger_zone = None
    trigger_rectangle = None
    trigger_te = None
    if isinstance(trigger_payload, dict):
        be = trigger_payload.get("best_event")
        if isinstance(be, dict):
            et = str(be.get("type") or "")
            e = be.get("evidence") if isinstance(be.get("evidence"), dict) else None
            if et == "raja_sr_touch" and isinstance(e, dict):
                trigger_zone = dict(e)
                trigger_zone["timeframe"] = be.get("timeframe")
            if et == "consolidation_rectangle_breakout" and isinstance(e, dict):
                trigger_rectangle = dict(e)
                trigger_rectangle["timeframe"] = be.get("timeframe")
            if et == "trend_exhaustion" and isinstance(e, dict):
                trigger_te = dict(e)
                trigger_te["timeframe"] = be.get("timeframe")

    payload = {
        "event": {
            "event_id": event_id,
            "trigger_type": trigger_type,
            "trigger_text": trigger_text,
            "trigger_payload": trigger_payload,
            "trigger_zone": trigger_zone,
            "trigger_rectangle": trigger_rectangle,
            "trigger_te": trigger_te,
            "symbol": symbol,
            "timeframe": event_timeframe,
            "snapshot_time_iso": _ts_to_iso(snapshot_time),
            "trend_tf": trend_tf,
            "exec_tf": exec_tf,
            "liquiditylevel_tf": liquiditylevel_tf,
        },
        "multi_tf_alignment": {"direction": direction, "consistency": consistency, "note": note},
        "market_state": {
            "session": current_session,
            "market_session": market_session,
            "current_quote": quote if isinstance(quote, dict) else None,
            "spread_pts": quote.get("spread") if isinstance(quote, dict) else None,
            "data_fresh": bool(snapshot_time and abs(now_ts - int(snapshot_time)) <= 3 * 3600),
            "vol_regime": vol_regime,
            "volume_activity": volume_activity,
            "upcoming_news_impact": upcoming_news_impact,
            "session_vp": session_vp,
        },
        "indicator_notes": indicator_notes,
        "market": market,
        "missing_indicators": missing,
        "constraints": {
            "output_format": "strict_json",
            "required_fields": [
                "signal",
                "confidence",
                "reasoning",
                "evidence_refs",
                "position_state",
                "decision_delta",
                "entry_type",
                "entry_price",
                "stop_loss",
                "take_profit",
                "risk_reward_ratio",
                "invalidation_condition",
                "trade_horizon",
            ],
            "output_schema": {
                "signal": {"type": "string", "enum": ["buy", "sell", "hold"]},
                "confidence": {"type": "integer", "minimum": 1, "maximum": 10, "description": "信号置信度，1-10"},
                "reasoning": {"type": "string", "description": "3-5句核心逻辑，引用上下文证据，避免模糊词"},
                "evidence_refs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "证据引用列表：填写 evidence_id（如 zone_M15_xxx / break_M15_xxx）",
                },
                "position_state": {
                    "type": "string",
                    "enum": ["flat", "long", "short"],
                    "description": "当前仓位状态（逻辑持仓，不代表真实账户）",
                },
                "decision_delta": {"type": "string", "description": "相对上一触发的变化点；若反转必须说明触发了哪条失效条件"},
                "entry_type": {"type": "string", "enum": ["market", "limit"]},
                "entry_price": {"type": "number"},
                "stop_loss": {"type": "number"},
                "take_profit": {"type": "array", "items": {"type": "number"}},
                "risk_reward_ratio": {"type": "number"},
                "invalidation_condition": {"type": "string"},
                "trade_horizon": {"type": "string", "enum": ["scalp", "intraday", "swing"]},
            },
        },
    }

    return _round3_any(payload)


def build_event_context(
    *,
    event_id: str,
    trigger_type: str,
    trigger_text: str,
    trigger_payload: Dict[str, Any] | None = None,
    symbol: str,
    event_timeframe: str,
    history_limits: Dict[str, int] | None = None,
    configs: dict | None = None,
) -> Dict[str, Any]:
    compute_limits = history_limits or {"H1": 400, "M15": 600, "H4": 200}
    ohlcv_payload_limits = {"H1": 25, "M15": 50, "H4": 15}
    base_tfs = {"H1", "M15", "H4", str(event_timeframe)}
    tfs_key = tuple(sorted(tf for tf in base_tfs if tf))

    latest_exec_t = None
    try:
        tail = historical_service.get_history(symbol=symbol, timeframe="M15", limit=1)
        if tail and isinstance(tail, list):
            latest_exec_t = int((tail[-1] or {}).get("time") or 0) or None
    except Exception:
        latest_exec_t = None

    key = (
        "event_context_v1",
        str(symbol),
        tfs_key,
        latest_exec_t,
        tuple(sorted((compute_limits or {}).items())),
        tuple(sorted((ohlcv_payload_limits or {}).items())),
        json.dumps((configs or {}).get("context_features") or {}, sort_keys=True, ensure_ascii=False),
        json.dumps(trigger_payload or {}, sort_keys=True, ensure_ascii=False),
    )

    now = time.time()
    with _CACHE_LOCK:
        hit = _EVENT_CONTEXT_CACHE.get(key)
        if hit is not None:
            ts, cached = hit
            if (now - ts) <= _EVENT_CONTEXT_CACHE_TTL_SEC and isinstance(cached, dict):
                _EVENT_CONTEXT_CACHE.move_to_end(key)
                payload = copy.deepcopy(cached)
                ev = payload.get("event")
                if isinstance(ev, dict):
                    ev["event_id"] = event_id
                    ev["trigger_type"] = trigger_type
                    ev["trigger_text"] = trigger_text
                    ev["trigger_payload"] = trigger_payload
                    ev["symbol"] = symbol
                    ev["timeframe"] = event_timeframe
                return payload
            _EVENT_CONTEXT_CACHE.pop(key, None)

    payload = _build_event_context_uncached(
        event_id=event_id,
        trigger_type=trigger_type,
        trigger_text=trigger_text,
        trigger_payload=trigger_payload,
        symbol=symbol,
        event_timeframe=event_timeframe,
        history_limits=history_limits,
        configs=configs,
    )

    with _CACHE_LOCK:
        _EVENT_CONTEXT_CACHE[key] = (now, copy.deepcopy(payload))
        _EVENT_CONTEXT_CACHE.move_to_end(key)
        while len(_EVENT_CONTEXT_CACHE) > _EVENT_CONTEXT_CACHE_MAX:
            _EVENT_CONTEXT_CACHE.popitem(last=False)

    return payload
