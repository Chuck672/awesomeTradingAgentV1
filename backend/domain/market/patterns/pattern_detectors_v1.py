from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from backend.domain.market.structure.swings import confirmed_structure_levels, detect_swings, structure_state_from_swings


def _atr14_from_bars(bars: List[Dict[str, Any]], period: int = 14) -> Optional[float]:
    if len(bars) < period + 1:
        return None
    trs: List[float] = []
    for i in range(1, len(bars)):
        h = float(bars[i]["high"])
        l = float(bars[i]["low"])
        pc = float(bars[i - 1]["close"])
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if len(trs) < period:
        return None
    return float(np.mean(trs[-period:]))


def _interval_iou(a0: int, a1: int, b0: int, b1: int) -> float:
    if a1 <= a0 or b1 <= b0:
        return 0.0
    inter = max(0, min(a1, b1) - max(a0, b0))
    union = max(a1, b1) - min(a0, b0)
    return float(inter) / float(max(1, union))


def detect_rectangle_ranges(
    bars: List[Dict[str, Any]],
    *,
    lookback_bars: int = 120,
    min_touches_per_side: int = 2,
    tolerance_atr_mult: float = 0.25,
    min_containment: float = 0.80,
    max_height_atr: float = 8.0,
    max_drift_atr: float = 3.0,
    max_efficiency: float = 0.45,
    emit: str = "best",  # best|distinct|all
    max_results: int = 50,
    distinct_no_overlap: bool = True,
    dedup_iou: float = 0.55,
) -> Dict[str, Any]:
    if len(bars) < int(lookback_bars):
        return {"items": [], "candidates": 0}

    win = bars[-int(lookback_bars) :]
    lb = len(win)

    win_min = 40 if lb >= 40 else max(4, lb)
    win_max = min(lb, 220)
    step = 5

    atr_base = _atr14_from_bars(win) or 0.0
    if atr_base <= 0:
        highs_all = np.array([float(b["high"]) for b in win], dtype=float)
        lows_all = np.array([float(b["low"]) for b in win], dtype=float)
        atr_base = float(np.mean(np.maximum(highs_all - lows_all, 1e-9)))

    def count_touch_events(highs: np.ndarray, lows: np.ndarray, top: float, bot: float, m: float) -> Tuple[int, int, List[str]]:
        top_hits = highs >= (top - m)
        bot_hits = lows <= (bot + m)
        if len(highs) < 12:
            t_cnt = int(np.sum(top_hits))
            b_cnt = int(np.sum(bot_hits))
            events: List[str] = []
            for i in range(len(highs)):
                if bool(top_hits[i]):
                    events.append("T")
                if bool(bot_hits[i]):
                    events.append("B")
            return t_cnt, b_cnt, events
        t_cnt = 0
        b_cnt = 0
        events: List[str] = []
        prev_t = False
        prev_b = False
        for i in range(len(highs)):
            cur_t = bool(top_hits[i])
            cur_b = bool(bot_hits[i])
            if cur_t and not prev_t:
                t_cnt += 1
                events.append("T")
            if cur_b and not prev_b:
                b_cnt += 1
                events.append("B")
            prev_t = cur_t
            prev_b = cur_b
        return t_cnt, b_cnt, events

    def has_rotation(events: List[str]) -> bool:
        if events.count("T") < 2 or events.count("B") < 2:
            return False
        s = "".join(events)
        return ("TBT" in s) or ("BTB" in s)

    def extend_until_breakout(
        start_idx: int,
        end_idx: int,
        top: float,
        bot: float,
        m: float,
        confirm_n: int = 2,
        max_end_idx: Optional[int] = None,
    ) -> Tuple[int, Optional[str], Optional[int], Optional[int]]:
        up = 0
        down = 0
        final_end = end_idx
        dirn: Optional[str] = None
        break_time: Optional[int] = None
        confirm_time: Optional[int] = None
        last_allowed = max_end_idx if isinstance(max_end_idx, int) else (len(win) - 1)
        for k in range(end_idx + 1, min(len(win), last_allowed + 1)):
            c = float(win[k]["close"])
            t = int(win[k]["time"])
            if c > top + m:
                up += 1
                down = 0
                if up == 1:
                    break_time = t
                if up >= int(confirm_n):
                    dirn = "up"
                    confirm_time = t
                    final_end = k
                    return final_end, dirn, break_time, confirm_time
            elif c < bot - m:
                down += 1
                up = 0
                if down == 1:
                    break_time = t
                if down >= int(confirm_n):
                    dirn = "down"
                    confirm_time = t
                    final_end = k
                    return final_end, dirn, break_time, confirm_time
            else:
                up = 0
                down = 0
                final_end = k
        return final_end, dirn, break_time, confirm_time

    candidates: List[Dict[str, Any]] = []

    for start in range(0, lb - win_min + 1, step):
        for w in range(win_min, min(win_max, lb - start) + 1, step):
            end = start + w
            sub = win[start:end]
            highs = np.array([float(b["high"]) for b in sub], dtype=float)
            lows = np.array([float(b["low"]) for b in sub], dtype=float)
            closes = np.array([float(b["close"]) for b in sub], dtype=float)

            top = float(np.percentile(highs, 95))
            bot = float(np.percentile(lows, 5))
            if not (np.isfinite(top) and np.isfinite(bot)) or top <= bot:
                continue

            height = float(top - bot)
            atr = float(atr_base)
            m = float(tolerance_atr_mult) * float(max(1e-9, atr))

            top_touch, bot_touch, events = count_touch_events(highs, lows, top, bot, m)
            if top_touch < int(min_touches_per_side) or bot_touch < int(min_touches_per_side):
                continue
            touch_sum_min = 6
            if w < 30:
                touch_sum_min = max(int(min_touches_per_side) * 2, min(6, max(4, int(w // 2))))
            if (top_touch + bot_touch) < int(touch_sum_min):
                continue
            if w >= 20 and not has_rotation(events):
                continue

            in_box = np.logical_and(closes >= bot - m, closes <= top + m)
            containment = float(np.mean(in_box))
            if containment < float(min_containment):
                continue

            height_atr = float(height / max(1e-9, atr))
            if height_atr > float(max_height_atr):
                continue

            net = float(abs(closes[-1] - closes[0]))
            drift_atr = float(net / max(1e-9, atr))
            if drift_atr > float(max_drift_atr):
                continue

            path = float(np.sum(np.abs(np.diff(closes)))) if len(closes) > 1 else 0.0
            efficiency = float(net / max(1e-9, path)) if path > 0 else 1.0
            if efficiency > float(max_efficiency):
                continue

            score_raw = (top_touch + bot_touch) * 10.0 + containment * 40.0 - height_atr * 8.0 - drift_atr * 8.0 - efficiency * 20.0
            score_raw += float(end) / float(max(1, lb)) * 5.0

            candidates.append(
                {
                    "from_idx": int(start),
                    "to_idx": int(end - 1),
                    "from_time": int(sub[0]["time"]),
                    "to_time": int(sub[-1]["time"]),
                    "top": float(top),
                    "bottom": float(bot),
                    "margin": float(m),
                    "touches": {"top": int(top_touch), "bottom": int(bot_touch), "events": events[-40:]},
                    "containment": float(containment),
                    "height_atr": float(height_atr),
                    "drift_atr": float(drift_atr),
                    "efficiency": float(efficiency),
                    "score_raw": float(score_raw),
                }
            )

    if not candidates:
        return {"items": [], "candidates": 0}

    candidates.sort(key=lambda x: float(x.get("score_raw") or -1e18), reverse=True)

    chosen: List[Dict[str, Any]] = []
    if str(emit) == "all":
        chosen = candidates[: int(max_results)]
    elif str(emit) == "distinct":
        for c in candidates:
            if len(chosen) >= int(max_results):
                break
            ok = True
            for p in chosen:
                if bool(distinct_no_overlap):
                    if not (int(c["to_time"]) < int(p["from_time"]) or int(c["from_time"]) > int(p["to_time"])):
                        ok = False
                        break
                else:
                    if _interval_iou(int(c["from_time"]), int(c["to_time"]), int(p["from_time"]), int(p["to_time"])) >= float(dedup_iou):
                        ok = False
                        break
            if ok:
                chosen.append(c)
        if not chosen:
            chosen = candidates[:1]
        chosen.sort(key=lambda x: int(x["from_time"]))
        if bool(distinct_no_overlap):
            filtered: List[Dict[str, Any]] = []
            last_end = -1
            for c in chosen:
                if int(c["from_time"]) > int(last_end):
                    filtered.append(c)
                    last_end = int(c["to_time"])
            chosen = filtered

        for i in range(len(chosen)):
            c = chosen[i]
            max_end_idx = None
            if bool(distinct_no_overlap) and i + 1 < len(chosen):
                nxt = chosen[i + 1]
                max_end_idx = int(nxt["from_idx"]) - 1
            final_end_idx, bdir, btime, ctime = extend_until_breakout(int(c["from_idx"]), int(c["to_idx"]), float(c["top"]), float(c["bottom"]), float(c["margin"]), confirm_n=2, max_end_idx=max_end_idx)
            c["to_idx"] = int(final_end_idx)
            c["to_time"] = int(win[final_end_idx]["time"])
            if bdir:
                c["breakout"] = {"direction": bdir, "break_time": btime, "confirm_time": ctime}
    else:
        chosen = candidates[:1]

    def to_item(c: Dict[str, Any], idx: int) -> Dict[str, Any]:
        score = max(0.0, min(100.0, 50.0 + (float(c.get("score_raw") or 0.0) / 10.0)))
        strength = "Strong" if (float(c.get("containment") or 0.0) >= 0.88 and float(c.get("height_atr") or 99.0) <= 6.0) else "Medium"
        ev = {
            "top": float(c["top"]),
            "bottom": float(c["bottom"]),
            "margin": float(c["margin"]),
            "touches": c.get("touches") or {},
            "from_time": int(c["from_time"]),
            "to_time": int(c["to_time"]),
            "containment": float(c.get("containment") or 0.0),
            "height_atr": float(c.get("height_atr") or 0.0),
            "drift_atr": float(c.get("drift_atr") or 0.0),
            "efficiency": float(c.get("efficiency") or 0.0),
        }
        if isinstance(c.get("breakout"), dict):
            ev["breakout"] = c["breakout"]
        return {
            "id": "rectangle_range" if str(emit) == "best" and idx == 0 else f"rectangle_range_{idx+1}",
            "type": "rectangle_range",
            "direction": "Neutral",
            "strength": strength,
            "score": float(score),
            "evidence": ev,
            "zone": {"type": "range_zone", "top": float(c["top"]), "bottom": float(c["bottom"])},
        }

    return {"items": [to_item(c, i) for i, c in enumerate(chosen)], "candidates": len(candidates)}


def detect_rectangle_range(
    bars: List[Dict[str, Any]],
    *,
    lookback_bars: int = 120,
    min_touches_per_side: int = 2,
    tolerance_atr_mult: float = 0.25,
    min_containment: float = 0.80,
    max_height_atr: float = 8.0,
    max_drift_atr: float = 3.0,
    max_efficiency: float = 0.45,
) -> Optional[Dict[str, Any]]:
    rep = detect_rectangle_ranges(
        bars,
        lookback_bars=lookback_bars,
        min_touches_per_side=min_touches_per_side,
        tolerance_atr_mult=tolerance_atr_mult,
        min_containment=min_containment,
        max_height_atr=max_height_atr,
        max_drift_atr=max_drift_atr,
        max_efficiency=max_efficiency,
        emit="best",
        max_results=1,
    )
    items = rep.get("items") if isinstance(rep, dict) else None
    if isinstance(items, list) and items:
        return items[0]
    return None


def detect_close_outside_level_zone(
    bars: List[Dict[str, Any]],
    *,
    levels: List[Dict[str, Any]],
    zones: List[Dict[str, Any]],
    close_buffer: float = 0.0,
    scan_mode: str = "realtime",  # realtime|historical
    lookback_bars: int = 300,
    confirm_mode: str = "one_body",  # one_body|two_close
    confirm_n: int = 2,
    max_events: int = 50,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not bars:
        return out

    atr14 = _atr14_from_bars(bars) or 0.0
    threshold_buf = float(close_buffer)
    body_margin = max(float(close_buffer), float(atr14) * 0.10)

    norm_zones: List[Dict[str, Any]] = []
    for z in zones:
        if not isinstance(z, dict):
            continue
        try:
            top = float(z.get("top")) if z.get("top") is not None else float(z.get("center")) + float(z.get("half_width_pips") or 0.0)
            bot = float(z.get("bottom")) if z.get("bottom") is not None else float(z.get("center")) - float(z.get("half_width_pips") or 0.0)
        except Exception:
            continue
        try:
            ft = int(z.get("from_time")) if z.get("from_time") is not None else 0
            tt = int(z.get("to_time")) if z.get("to_time") is not None else 0
        except Exception:
            ft, tt = 0, 0
        if ft <= 0 or tt <= 0 or tt <= ft:
            continue
        norm_zones.append({"top": top, "bottom": bot, "from_time": ft, "to_time": tt, "source_level": z.get("source_level"), "kind": (z.get("source_level") or {}).get("kind") if isinstance(z.get("source_level"), dict) else z.get("kind")})

    if not norm_zones:
        return out

    def in_active(z: Dict[str, Any], t: int) -> bool:
        return int(z["from_time"]) <= int(t) <= int(z["to_time"])

    def is_bull_break(bar: Dict[str, Any], z: Dict[str, Any]) -> bool:
        c = float(bar["close"])
        o = float(bar["open"])
        top = float(z["top"])
        buf = float(threshold_buf)
        if str(confirm_mode) == "one_body":
            return (c > top + buf) and (o >= top - float(body_margin))
        return c > top + buf

    def is_bear_break(bar: Dict[str, Any], z: Dict[str, Any]) -> bool:
        c = float(bar["close"])
        o = float(bar["open"])
        bot = float(z["bottom"])
        buf = float(threshold_buf)
        if str(confirm_mode) == "one_body":
            return (c < bot - buf) and (o <= bot + float(body_margin))
        return c < bot - buf

    def emit_event(z: Dict[str, Any], direction: str, trigger_time: int, confirm_time: int, bar: Dict[str, Any]) -> None:
        top = float(z["top"])
        bot = float(z["bottom"])
        clipped_to = int(min(int(z["to_time"]), int(confirm_time)))
        ev = {
            "zone": {"top": top, "bottom": bot, "from_time": int(z["from_time"]), "to_time": int(clipped_to), "kind": z.get("kind"), "to_time_raw": int(z["to_time"])},
            "direction": direction,
            "trigger_time": int(trigger_time),
            "confirm_time": int(confirm_time),
            "confirm_mode": str(confirm_mode),
            "buffer": float(threshold_buf),
            "body_margin": float(body_margin),
            "bar_time": int(bar["time"]),
            "close": float(bar["close"]),
            "open": float(bar["open"]),
        }
        out.append({"id": "close_outside_zone_up" if direction == "up" else "close_outside_zone_down", "type": "close_outside_level_zone", "direction": "Bullish" if direction == "up" else "Bearish", "strength": "Strong" if str(confirm_mode) == "two_close" else "Medium", "score": 75.0 if str(confirm_mode) == "two_close" else 70.0, "evidence": ev})

    mode = str(scan_mode)
    if mode == "historical":
        start_idx = max(0, len(bars) - int(lookback_bars))
        triggered: List[bool] = [False] * len(norm_zones)

        if str(confirm_mode) == "two_close":
            n = max(2, int(confirm_n))
            for i in range(start_idx + n - 1, len(bars)):
                t = int(bars[i]["time"])
                for zi, z in enumerate(norm_zones):
                    if triggered[zi] or not in_active(z, t):
                        continue
                    ok_up = True
                    ok_dn = True
                    for k in range(i - n + 1, i + 1):
                        ok_up = ok_up and is_bull_break(bars[k], z)
                        ok_dn = ok_dn and is_bear_break(bars[k], z)
                    if ok_up:
                        emit_event(z, "up", int(bars[i - n + 1]["time"]), int(bars[i]["time"]), bars[i])
                        triggered[zi] = True
                    elif ok_dn:
                        emit_event(z, "down", int(bars[i - n + 1]["time"]), int(bars[i]["time"]), bars[i])
                        triggered[zi] = True
                if len(out) >= int(max_events):
                    return out[: int(max_events)]
        else:
            for i in range(start_idx, len(bars)):
                t = int(bars[i]["time"])
                for zi, z in enumerate(norm_zones):
                    if triggered[zi] or not in_active(z, t):
                        continue
                    if is_bull_break(bars[i], z):
                        emit_event(z, "up", t, t, bars[i])
                        triggered[zi] = True
                    elif is_bear_break(bars[i], z):
                        emit_event(z, "down", t, t, bars[i])
                        triggered[zi] = True
                if len(out) >= int(max_events):
                    return out[: int(max_events)]
        return out[: int(max_events)]

    last_i = len(bars) - 1
    t_last = int(bars[last_i]["time"])
    if str(confirm_mode) == "two_close":
        n = max(2, int(confirm_n))
        if len(bars) < n:
            return out
        for z in norm_zones:
            if not in_active(z, t_last):
                continue
            ok_up = True
            ok_dn = True
            for k in range(last_i - n + 1, last_i + 1):
                ok_up = ok_up and is_bull_break(bars[k], z)
                ok_dn = ok_dn and is_bear_break(bars[k], z)
            if ok_up:
                emit_event(z, "up", int(bars[last_i - n + 1]["time"]), t_last, bars[last_i])
            elif ok_dn:
                emit_event(z, "down", int(bars[last_i - n + 1]["time"]), t_last, bars[last_i])
            if len(out) >= int(max_events):
                break
    else:
        for z in norm_zones:
            if not in_active(z, t_last):
                continue
            if is_bull_break(bars[last_i], z):
                emit_event(z, "up", t_last, t_last, bars[last_i])
            elif is_bear_break(bars[last_i], z):
                emit_event(z, "down", t_last, t_last, bars[last_i])
            if len(out) >= int(max_events):
                break

    return out[: int(max_events)]


def detect_breakout_retest_hold(
    bars: List[Dict[str, Any]],
    *,
    levels: List[Dict[str, Any]],
    zones: List[Dict[str, Any]],
    scan_mode: str = "realtime",  # realtime|historical
    lookback_bars: int = 300,
    confirm_mode: str = "one_body",  # one_body|two_close
    confirm_n: int = 2,
    retest_window_bars: int = 16,
    continue_window_bars: int = 8,
    buffer: float = 0.0,
    pullback_margin: float = 0.0,
    max_events: int = 50,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not bars:
        return out

    lb = int(lookback_bars)
    if len(bars) < lb:
        return out
    win = bars[-lb:]

    atr14 = _atr14_from_bars(win) or 0.0
    threshold_buf = float(buffer)
    body_margin = max(threshold_buf, float(atr14) * 0.10)
    pb_margin = float(pullback_margin) if float(pullback_margin) > 0 else max(threshold_buf, float(atr14) * 0.15)

    norm_zones: List[Dict[str, Any]] = []
    for z in zones:
        if not isinstance(z, dict):
            continue
        try:
            top = float(z.get("top"))
            bot = float(z.get("bottom"))
            ft = int(z.get("from_time"))
            tt = int(z.get("to_time"))
        except Exception:
            continue
        if ft <= 0 or tt <= 0 or tt <= ft or not (np.isfinite(top) and np.isfinite(bot)) or top <= bot:
            continue
        norm_zones.append({"top": top, "bottom": bot, "from_time": ft, "to_time": tt, "kind": (z.get("source_level") or {}).get("kind") if isinstance(z.get("source_level"), dict) else z.get("kind")})

    if not norm_zones:
        return out

    def in_active(z: Dict[str, Any], t: int) -> bool:
        return int(z["from_time"]) <= int(t) <= int(z["to_time"])

    def bull_close_outside(bar: Dict[str, Any], z: Dict[str, Any]) -> bool:
        return float(bar["close"]) > float(z["top"]) + threshold_buf

    def bear_close_outside(bar: Dict[str, Any], z: Dict[str, Any]) -> bool:
        return float(bar["close"]) < float(z["bottom"]) - threshold_buf

    def bull_break_confirmed_at(i: int, z: Dict[str, Any]) -> Tuple[bool, Optional[int], Optional[int]]:
        if str(confirm_mode) == "two_close":
            n = max(2, int(confirm_n))
            if i - n + 1 < 0:
                return False, None, None
            for k in range(i - n + 1, i + 1):
                if not bull_close_outside(win[k], z):
                    return False, None, None
            return True, int(win[i - n + 1]["time"]), int(win[i]["time"])
        bar = win[i]
        c = float(bar["close"])
        o = float(bar["open"])
        top = float(z["top"])
        if (c > top + threshold_buf) and (o >= top - body_margin):
            t = int(bar["time"])
            return True, t, t
        return False, None, None

    def bear_break_confirmed_at(i: int, z: Dict[str, Any]) -> Tuple[bool, Optional[int], Optional[int]]:
        if str(confirm_mode) == "two_close":
            n = max(2, int(confirm_n))
            if i - n + 1 < 0:
                return False, None, None
            for k in range(i - n + 1, i + 1):
                if not bear_close_outside(win[k], z):
                    return False, None, None
            return True, int(win[i - n + 1]["time"]), int(win[i]["time"])
        bar = win[i]
        c = float(bar["close"])
        o = float(bar["open"])
        bot = float(z["bottom"])
        if (c < bot - threshold_buf) and (o <= bot + body_margin):
            t = int(bar["time"])
            return True, t, t
        return False, None, None

    def bull_retest_at(i: int, z: Dict[str, Any]) -> bool:
        bar = win[i]
        low = float(bar["low"])
        close = float(bar["close"])
        top = float(z["top"])
        return (low <= top + pb_margin) and (close >= top - pb_margin)

    def bear_retest_at(i: int, z: Dict[str, Any]) -> bool:
        bar = win[i]
        high = float(bar["high"])
        close = float(bar["close"])
        bot = float(z["bottom"])
        return (high >= bot - pb_margin) and (close <= bot + pb_margin)

    def bull_continue_at(i: int, z: Dict[str, Any]) -> bool:
        return bull_close_outside(win[i], z)

    def bear_continue_at(i: int, z: Dict[str, Any]) -> bool:
        return bear_close_outside(win[i], z)

    events: List[Dict[str, Any]] = []
    for z in norm_zones:
        state = "IDLE"
        brk_trigger_time = None
        brk_confirm_time = None
        brk_dir = None
        retest_time = None

        for i in range(len(win)):
            t = int(win[i]["time"])
            if not in_active(z, t):
                continue

            if state == "IDLE":
                ok, trig, conf = bull_break_confirmed_at(i, z)
                if ok:
                    state = "BROKEN"
                    brk_dir = "up"
                    brk_trigger_time = trig
                    brk_confirm_time = conf
                    continue
                ok, trig, conf = bear_break_confirmed_at(i, z)
                if ok:
                    state = "BROKEN"
                    brk_dir = "down"
                    brk_trigger_time = trig
                    brk_confirm_time = conf
                    continue

            elif state == "BROKEN":
                if brk_confirm_time is not None:
                    pass
                if brk_confirm_time is not None and t < int(brk_confirm_time):
                    continue
                if "_confirm_idx" not in z:
                    ci = None
                    for k in range(len(win)):
                        if int(win[k]["time"]) == int(brk_confirm_time):
                            ci = k
                            break
                    z["_confirm_idx"] = ci if ci is not None else i
                ci = int(z.get("_confirm_idx") or i)
                if i - ci > int(retest_window_bars):
                    state = "FAILED"
                    break
                if brk_dir == "up":
                    if bull_retest_at(i, z):
                        retest_time = t
                        state = "RETESTED"
                        z["_retest_idx"] = i
                        continue
                else:
                    if bear_retest_at(i, z):
                        retest_time = t
                        state = "RETESTED"
                        z["_retest_idx"] = i
                        continue

            elif state == "RETESTED":
                ri = int(z.get("_retest_idx") or i)
                if i - ri > int(continue_window_bars):
                    state = "FAILED"
                    break
                if brk_dir == "up":
                    if bull_continue_at(i, z):
                        cont_time = t
                        clipped_to = int(min(int(z["to_time"]), int(cont_time)))
                        events.append(
                            {
                                "id": "breakout_retest_hold_up" if brk_dir == "up" else "breakout_retest_hold_down",
                                "type": "breakout_retest_hold",
                                "direction": "Bullish" if brk_dir == "up" else "Bearish",
                                "strength": "Strong" if str(confirm_mode) == "two_close" else "Medium",
                                "score": 82.0 if str(confirm_mode) == "two_close" else 78.0,
                                "evidence": {
                                    "zone": {"top": float(z["top"]), "bottom": float(z["bottom"]), "from_time": int(z["from_time"]), "to_time": int(clipped_to), "to_time_raw": int(z["to_time"]), "kind": z.get("kind")},
                                    "breakout": {"direction": brk_dir, "trigger_time": int(brk_trigger_time or brk_confirm_time or t), "confirm_time": int(brk_confirm_time or t), "confirm_mode": str(confirm_mode), "confirm_n": int(confirm_n)},
                                    "pullback": {"retest_time": int(retest_time or t), "margin": float(pb_margin)},
                                    "continuation": {"continue_time": int(cont_time)},
                                    "buffer": float(threshold_buf),
                                    "body_margin": float(body_margin),
                                },
                            }
                        )
                        state = "DONE"
                        break
                else:
                    if bear_continue_at(i, z):
                        cont_time = t
                        clipped_to = int(min(int(z["to_time"]), int(cont_time)))
                        events.append(
                            {
                                "id": "breakout_retest_hold_down",
                                "type": "breakout_retest_hold",
                                "direction": "Bearish",
                                "strength": "Strong" if str(confirm_mode) == "two_close" else "Medium",
                                "score": 82.0 if str(confirm_mode) == "two_close" else 78.0,
                                "evidence": {
                                    "zone": {"top": float(z["top"]), "bottom": float(z["bottom"]), "from_time": int(z["from_time"]), "to_time": int(clipped_to), "to_time_raw": int(z["to_time"]), "kind": z.get("kind")},
                                    "breakout": {"direction": brk_dir, "trigger_time": int(brk_trigger_time or brk_confirm_time or t), "confirm_time": int(brk_confirm_time or t), "confirm_mode": str(confirm_mode), "confirm_n": int(confirm_n)},
                                    "pullback": {"retest_time": int(retest_time or t), "margin": float(pb_margin)},
                                    "continuation": {"continue_time": int(cont_time)},
                                    "buffer": float(threshold_buf),
                                    "body_margin": float(body_margin),
                                },
                            }
                        )
                        state = "DONE"
                        break

    if not events:
        return out

    if str(scan_mode) == "realtime":
        t_last = int(win[-1]["time"])
        for e in events:
            ct = ((e.get("evidence") or {}).get("continuation") or {}).get("continue_time")
            if int(ct or 0) == t_last:
                out.append(e)
                if len(out) >= int(max_events):
                    break
        return out[: int(max_events)]

    events.sort(key=lambda x: int((((x.get("evidence") or {}).get("continuation") or {}).get("continue_time") or 0)))
    return events[: int(max_events)]


def detect_bos_choch(
    bars: List[Dict[str, Any]],
    *,
    lookback_bars: int = 220,
    pivot_left: int = 3,
    pivot_right: int = 3,
    buffer: float = 0.0,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    min_bars = max(5, int(pivot_left) + int(pivot_right) + 3)
    if len(bars) < max(min_bars, int(lookback_bars)):
        return out
    win = bars[-int(lookback_bars) :]
    swings = detect_swings(win, left=int(pivot_left), right=int(pivot_right))
    structure = structure_state_from_swings(swings)
    lv = confirmed_structure_levels(swings)
    sh = lv.get("structure_high")
    sl = lv.get("structure_low")
    if sh is None:
        highs = [s for s in swings if s.kind == "H"]
        if highs:
            sh = float(highs[-1].price)
    if sl is None:
        lows = [s for s in swings if s.kind == "L"]
        if lows:
            sl = float(lows[-1].price)
    if sh is None and sl is None:
        return out
    last = win[-1]
    t = int(last["time"])
    c = float(last["close"])

    if structure == "HH_HL":
        if sh is not None and c > float(sh) + buffer:
            out.append({"id": "bos_up", "type": "bos", "direction": "Bullish", "strength": "Medium", "score": 78.0, "evidence": {"structure": structure, "level": float(sh), "bar_time": t, "close": c, "buffer": buffer}})
        if sl is not None and c < float(sl) - buffer:
            out.append({"id": "choch_down", "type": "choch", "direction": "Bearish", "strength": "Strong", "score": 85.0, "evidence": {"structure": structure, "level": float(sl), "bar_time": t, "close": c, "buffer": buffer}})
    elif structure == "LH_LL":
        if sl is not None and c < float(sl) - buffer:
            out.append({"id": "bos_down", "type": "bos", "direction": "Bearish", "strength": "Medium", "score": 78.0, "evidence": {"structure": structure, "level": float(sl), "bar_time": t, "close": c, "buffer": buffer}})
        if sh is not None and c > float(sh) + buffer:
            out.append({"id": "choch_up", "type": "choch", "direction": "Bullish", "strength": "Strong", "score": 85.0, "evidence": {"structure": structure, "level": float(sh), "bar_time": t, "close": c, "buffer": buffer}})
    else:
        if sh is not None and c > float(sh) + buffer:
            out.append({"id": "bos_up", "type": "bos", "direction": "Bullish", "strength": "Weak", "score": 70.0, "evidence": {"structure": structure, "level": float(sh), "bar_time": t, "close": c, "buffer": buffer}})
        elif sl is not None and c < float(sl) - buffer:
            out.append({"id": "bos_down", "type": "bos", "direction": "Bearish", "strength": "Weak", "score": 70.0, "evidence": {"structure": structure, "level": float(sl), "bar_time": t, "close": c, "buffer": buffer}})

    return out[:8]
