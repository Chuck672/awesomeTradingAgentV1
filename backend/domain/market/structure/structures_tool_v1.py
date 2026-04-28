from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import datetime as dt

from backend.domain.market.structure.swings import detect_swings


def _prev_day_hl(bars: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not bars:
        return []
    try:
        last_ts = int(bars[-1].get("time"))
    except Exception:
        return []
    last_day = dt.datetime.utcfromtimestamp(last_ts).date()
    prev_day = last_day - dt.timedelta(days=1)

    hi = None
    lo = None
    for b in bars:
        try:
            day = dt.datetime.utcfromtimestamp(int(b.get("time"))).date()
        except Exception:
            continue
        if day != prev_day:
            continue
        try:
            h = float(b.get("high"))
            l = float(b.get("low"))
        except Exception:
            continue
        hi = h if hi is None else max(hi, h)
        lo = l if lo is None else min(lo, l)
    if hi is None or lo is None:
        return []
    return [{"type": "level", "kind": "prev_day_high", "price": hi}, {"type": "level", "kind": "prev_day_low", "price": lo}]


def _swing_levels(bars: List[Dict[str, Any]], *, left: int = 3, right: int = 3, max_levels: int = 8) -> List[Dict[str, Any]]:
    swings = detect_swings(bars, left=left, right=right, max_points=max(20, int(max_levels) * 6))
    out: List[Dict[str, Any]] = []
    for s in swings:
        out.append({"type": "level", "kind": "swing_high" if s.kind == "H" else "swing_low", "price": float(s.price), "time": int(s.time)})
    out = sorted(out, key=lambda x: x.get("time", 0), reverse=True)[: max_levels * 2]
    dedup: List[Dict[str, Any]] = []
    for it in out:
        p = float(it["price"])
        if any(abs(p - float(j["price"])) < 1e-6 for j in dedup):
            continue
        dedup.append(it)
        if len(dedup) >= max_levels:
            break
    return dedup


def _infer_price_digits(bars: List[Dict[str, Any]]) -> int:
    if not bars:
        return 0
    samples: List[float] = []
    for b in bars[-300:]:
        try:
            samples.append(float(b.get("close")))
        except Exception:
            continue
    if not samples:
        return 0
    for digits, scale in [(0, 1), (1, 10), (2, 100), (3, 1000), (4, 10000), (5, 100000)]:
        ok = 0
        for v in samples:
            if abs(round(v * scale) - v * scale) < 1e-6:
                ok += 1
        if ok / max(1, len(samples)) >= 0.8:
            return digits
    return 2


def _pip_size_from_digits(digits: int) -> float:
    try:
        d = int(digits)
    except Exception:
        d = 2
    if d >= 2:
        return float(10 ** (-(d - 1)))
    return 1.0


def tool_structure_level_generator(payload: Dict[str, Any]) -> Dict[str, Any]:
    bars_by_tf = payload.get("bars_by_tf") if isinstance(payload.get("bars_by_tf"), dict) else {}
    primary_tf = str(payload.get("primary_timeframe") or "30m")
    lg = payload.get("level_generator") if isinstance(payload.get("level_generator"), dict) else {}
    sources = lg.get("sources") if isinstance(lg.get("sources"), list) else []
    output = lg.get("output") if isinstance(lg.get("output"), dict) else {}
    max_levels = int(output.get("max_levels") or 8)
    zone_half_width = None
    zone_max_age_bars = 300
    try:
        z = output.get("zone_half_width_pips") or {}
        if isinstance(z, dict) and isinstance(z.get("default"), dict):
            zone_half_width = float(z["default"].get("pips") or 0)
    except Exception:
        zone_half_width = None
    try:
        zone_max_age_bars = int(output.get("zone_max_age_bars") or 300)
    except Exception:
        zone_max_age_bars = 300

    levels: List[Dict[str, Any]] = []
    for s in sources:
        if not isinstance(s, dict):
            continue
        t = str(s.get("type") or "")
        if t == "prev_day_high_low":
            bars = bars_by_tf.get(primary_tf) or []
            levels.extend(_prev_day_hl(bars))
        elif t in ("htf_swing_points", "fractal_levels"):
            tf = str(s.get("timeframe") or "4h")
            bars = bars_by_tf.get(tf) or bars_by_tf.get(primary_tf) or []
            left = int(s.get("pivot_left") or s.get("fractal_left") or 3)
            right = int(s.get("pivot_right") or s.get("fractal_right") or 3)
            levels.extend(_swing_levels(bars, left=left, right=right, max_levels=max_levels))
        elif t == "prev_week_high_low":
            continue
        elif t == "session_high_low":
            continue
        elif t == "vp_poc":
            continue

    if len(levels) > max_levels:
        levels = levels[:max_levels]

    bars_primary = bars_by_tf.get(primary_tf) or []
    bar_interval_sec = 0
    if isinstance(bars_primary, list) and len(bars_primary) >= 3:
        try:
            ts = [int(b.get("time")) for b in bars_primary[-200:] if b.get("time") is not None]
            diffs = [ts[i] - ts[i - 1] for i in range(1, len(ts)) if ts[i] - ts[i - 1] > 0]
            diffs_sorted = sorted(diffs)
            bar_interval_sec = diffs_sorted[len(diffs_sorted) // 2] if diffs_sorted else 0
        except Exception:
            bar_interval_sec = 0
    if not bar_interval_sec:
        tf = str(primary_tf)
        if tf.endswith("m"):
            bar_interval_sec = int(tf[:-1]) * 60 if tf[:-1].isdigit() else 1800
        elif tf.endswith("h"):
            bar_interval_sec = int(tf[:-1]) * 3600 if tf[:-1].isdigit() else 3600
        elif tf.endswith("d"):
            bar_interval_sec = 86400
        else:
            bar_interval_sec = 1800

    default_from_time = None
    if isinstance(bars_primary, list) and bars_primary:
        try:
            last_ts = int(bars_primary[-1].get("time"))
            last_day = dt.datetime.utcfromtimestamp(last_ts).date()
            default_from_time = int(dt.datetime(last_day.year, last_day.month, last_day.day, 0, 0, 0).timestamp())
        except Exception:
            default_from_time = None

    digits = _infer_price_digits(bars_primary if isinstance(bars_primary, list) else [])
    pip_size = _pip_size_from_digits(digits)

    zones: List[Dict[str, Any]] = []
    if output.get("emit_zone") and zone_half_width and zone_half_width > 0:
        for lv in levels:
            try:
                center = float(lv.get("price"))
            except Exception:
                continue
            half = float(zone_half_width) * float(pip_size)
            from_time = None
            if lv.get("time") is not None:
                try:
                    from_time = int(lv.get("time"))
                except Exception:
                    from_time = None
            if from_time is None:
                from_time = default_from_time
            if from_time is None and isinstance(bars_primary, list) and bars_primary:
                try:
                    from_time = int(bars_primary[0].get("time"))
                except Exception:
                    from_time = None
            if from_time is None:
                from_time = 0
            to_time = int(from_time + max(1, zone_max_age_bars) * max(1, bar_interval_sec))
            zones.append({"type": "zone", "center": center, "half_width_pips": float(zone_half_width), "pip_size": float(pip_size), "half_width": float(half), "top": center + float(half), "bottom": center - float(half), "from_time": int(from_time), "to_time": int(to_time), "source_level": lv})

    if payload.get("_debug"):
        bars = bars_by_tf.get(primary_tf) or []
        prev_cnt = 0
        if bars:
            try:
                last_ts = int(bars[-1].get("time"))
                last_day = dt.datetime.utcfromtimestamp(last_ts).date()
                prev_day = last_day - dt.timedelta(days=1)
                prev_cnt = sum(1 for x in bars if dt.datetime.utcfromtimestamp(int(x.get("time"))).date() == prev_day)
            except Exception:
                prev_cnt = -1
        return {"levels": levels, "zones": zones, "_debug": {"primary_timeframe": primary_tf, "bars_by_tf_keys": list(bars_by_tf.keys())[:10], "bars_len_primary": len(bars) if isinstance(bars, list) else -1, "sample_bar0": (bars[0] if isinstance(bars, list) and bars else None), "prev_day_cnt": prev_cnt, "sources": sources}}

    return {"levels": levels, "zones": zones}

