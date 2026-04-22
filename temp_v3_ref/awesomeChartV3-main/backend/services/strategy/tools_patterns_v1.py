from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from backend.services.chart_scene.patterns import detect_candlestick_patterns
from backend.services.chart_scene.indicators import detect_swings, structure_state_from_swings, confirmed_structure_levels


def _bars_for_tf(bars_by_tf: Dict[str, Any], tf: str) -> List[Dict[str, Any]]:
    v = bars_by_tf.get(tf)
    return v if isinstance(v, list) else []


def _atr14_from_bars(bars: List[Dict[str, Any]], period: int = 14) -> Optional[float]:
    """
    轻量 ATR（仅用于 detector 容错与阈值转换）；不依赖 indicator 计算结果。
    """
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


def _last_close(bars: List[Dict[str, Any]]) -> Optional[float]:
    if not bars:
        return None
    try:
        return float(bars[-1]["close"])
    except Exception:
        return None


def _levels_and_zones(structures_levels: Any, structures_zones: Any) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    levels = structures_levels if isinstance(structures_levels, list) else []
    zones = structures_zones if isinstance(structures_zones, list) else []
    return levels, zones


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
    """
    输出多个箱体结构：
    - emit=best：只返回最佳 1 个
    - emit=distinct：按时间 IoU 去重后返回多个
    - emit=all：返回所有通过过滤的候选（可能很多）
    """
    if len(bars) < int(lookback_bars):
        return {"items": [], "candidates": 0}

    win = bars[-int(lookback_bars) :]
    lb = len(win)

    # 扫描窗口：宽度范围与步长
    win_min = 40 if lb >= 40 else max(4, lb)
    win_max = min(lb, 220)
    step = 5

    atr_base = _atr14_from_bars(win) or 0.0
    if atr_base <= 0:
        # fallback：用 TR 的均值近似
        highs_all = np.array([float(b["high"]) for b in win], dtype=float)
        lows_all = np.array([float(b["low"]) for b in win], dtype=float)
        atr_base = float(np.mean(np.maximum(highs_all - lows_all, 1e-9)))

    def count_touch_events(highs: np.ndarray, lows: np.ndarray, top: float, bot: float, m: float) -> Tuple[int, int, List[str]]:
        """
        触边计数：进入 edge zone 视为一次触及（去抖：连续触及只算一次）
        返回：(top_touches, bot_touches, events序列['T'/'B'])
        """
        top_hits = highs >= (top - m)
        bot_hits = lows <= (bot + m)
        # 小窗口下（例如单测/极短样本）不做去抖，否则连续触边会被计为 1 次，导致无法触发
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
        # 至少出现 T 与 B 各 2 次，并且序列里有轮转（如 T->B->T 或 B->T->B）
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
        """
        延伸箱体直到“有效突破”：
        - 连续 confirm_n 根 close 出界（向上/向下）认为突破确认
        - wick 刺破不算突破
        返回：(final_end_idx, direction, break_time, confirm_time)
        """
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

            # 边界估计：分位数减少极端 wick 影响
            top = float(np.percentile(highs, 95))
            bot = float(np.percentile(lows, 5))
            if not (np.isfinite(top) and np.isfinite(bot)) or top <= bot:
                continue

            height = float(top - bot)
            atr = float(atr_base)
            m = float(tolerance_atr_mult) * float(max(1e-9, atr))

            # 触边事件（去抖）
            top_touch, bot_touch, events = count_touch_events(highs, lows, top, bot, m)
            if top_touch < int(min_touches_per_side) or bot_touch < int(min_touches_per_side):
                continue
            # 小窗口下不强制 sum>=6（否则样例/短数据无法触发）
            touch_sum_min = 6
            if w < 30:
                touch_sum_min = max(int(min_touches_per_side) * 2, min(6, max(4, int(w // 2))))
            if (top_touch + bot_touch) < int(touch_sum_min):
                continue
            # 小窗口下轮转特征不稳定，不强制要求；中长窗口要求轮转以显著降低误报
            if w >= 20 and not has_rotation(events):
                continue

            # 收盘应多数在箱体内
            in_box = np.logical_and(closes >= bot - m, closes <= top + m)
            containment = float(np.mean(in_box))
            if containment < float(min_containment):
                continue

            # 过滤趋势段：高度/ATR、净位移/ATR、效率
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

            # 打分：触边越多越好；containment 越高越好；高度/位移/效率越小越好
            score_raw = (top_touch + bot_touch) * 10.0 + containment * 40.0 - height_atr * 8.0 - drift_atr * 8.0 - efficiency * 20.0
            # 偏好靠近现在的箱体（用于研究/可视化）
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
        # all：返回所有通过过滤的候选窗口（注意：会有大量重复/重叠）
        chosen = candidates[: int(max_results)]
    elif str(emit) == "distinct":
        # distinct：输出“合并后的箱体簇（distinct structures）”
        # 用户要求：不允许 overlap / containment（默认 strict）
        # 策略：按 score 贪心选取 + 非重叠约束
        for c in candidates:
            if len(chosen) >= int(max_results):
                break
            ok = True
            for p in chosen:
                if bool(distinct_no_overlap):
                    # 严格：时间区间不允许相交（也就不存在包含）
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
        # 强制不重叠（也就不存在包含）：按起点排序，过滤掉与上一个相交的结构
        chosen.sort(key=lambda x: int(x["from_time"]))
        if bool(distinct_no_overlap):
            filtered: List[Dict[str, Any]] = []
            last_end = -1
            for c in chosen:
                if int(c["from_time"]) > int(last_end):
                    filtered.append(c)
                    last_end = int(c["to_time"])
            chosen = filtered

        # 为了保证“最终结构不重叠”，再做一次延伸（突破确认）并裁剪到下一段开始之前
        for i in range(len(chosen)):
            c = chosen[i]
            max_end_idx = None
            if bool(distinct_no_overlap) and i + 1 < len(chosen):
                # 不允许越过下一段起点
                nxt = chosen[i + 1]
                max_end_idx = int(nxt["from_idx"]) - 1
            final_end_idx, bdir, btime, ctime = extend_until_breakout(
                int(c["from_idx"]),
                int(c["to_idx"]),
                float(c["top"]),
                float(c["bottom"]),
                float(c["margin"]),
                confirm_n=2,
                max_end_idx=max_end_idx,
            )
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
    """
    兼容旧接口：仅返回最佳 1 个箱体（或 None）。
    """
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
    """
    Close Outside Level Zone（更偏交易）：
    - 仅使用“带时间范围”的 zones（from_time/to_time + top/bottom），不再把 level 当作贯穿全图的水平线
    - 突破以 close 为准，影线刺破不算
    - 支持 realtime（只看最后一根）与 historical（扫描区间内所有触发）
    - confirm_mode:
        * one_body（默认）：1 根实体收盘确认（body 在 zone 外）
        * two_close：连续 N 根 close 在 zone 外（默认 N=2）
    """
    out: List[Dict[str, Any]] = []
    if not bars:
        return out

    # buffer：用于“close 是否出界”的阈值（用户可显式传 close_buffer）
    # body_margin：用于 one_body 模式下的实体确认容差（避免要求 open 也必须在区间外导致几乎无信号）
    atr14 = _atr14_from_bars(bars) or 0.0
    threshold_buf = float(close_buffer)
    body_margin = max(float(close_buffer), float(atr14) * 0.10)

    # normalize/keep only time-bounded zones
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
        # 必须具备时间范围；若没有则跳过（由 structure 工具保证）
        if ft <= 0 or tt <= 0 or tt <= ft:
            continue
        norm_zones.append(
            {
                "top": top,
                "bottom": bot,
                "from_time": ft,
                "to_time": tt,
                "source_level": z.get("source_level"),
                "kind": (z.get("source_level") or {}).get("kind") if isinstance(z.get("source_level"), dict) else z.get("kind"),
            }
        )

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
            # 1 根实体收盘确认（偏交易口径）：
            # - close 必须在 zone 外
            # - open 不要求也在 zone 外（否则太苛刻，绝大多数突破K会从区间内开盘），
            #   但要求 open 至少不“深度回到 zone 内”，默认允许贴边/轻微回踩：
            #   open >= top - buf
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
        # 交易语义：一旦该 zone 被“有效突破确认”，在本 detector 的视角中 zone 到此结束
        clipped_to = int(min(int(z["to_time"]), int(confirm_time)))
        ev = {
            "zone": {
                "top": top,
                "bottom": bot,
                "from_time": int(z["from_time"]),
                "to_time": int(clipped_to),
                "kind": z.get("kind"),
                # 便于调试：原始结构 zone 的结束时间
                "to_time_raw": int(z["to_time"]),
            },
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
        out.append(
            {
                "id": "close_outside_zone_up" if direction == "up" else "close_outside_zone_down",
                "type": "close_outside_level_zone",
                "direction": "Bullish" if direction == "up" else "Bearish",
                "strength": "Strong" if str(confirm_mode) == "two_close" else "Medium",
                "score": 75.0 if str(confirm_mode) == "two_close" else 70.0,
                "evidence": ev,
            }
        )

    mode = str(scan_mode)
    if mode == "historical":
        start_idx = max(0, len(bars) - int(lookback_bars))
        # 对每个 zone 只发一次事件（触发后视为失效），避免历史扫描重复输出
        triggered: List[bool] = [False] * len(norm_zones)

        if str(confirm_mode) == "two_close":
            n = max(2, int(confirm_n))
            for i in range(start_idx + n - 1, len(bars)):
                t = int(bars[i]["time"])
                for zi, z in enumerate(norm_zones):
                    if triggered[zi] or not in_active(z, t):
                        continue
                    # 最近 n 根 close 都在 zone 外（同方向）
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

    # realtime: only evaluate last bar (and previous bars if needed)
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
    """
    Breakout + Pullback (Retest Hold)（交易化 v2）：
    - 仅基于“带时间范围”的 level zones（top/bottom/from_time/to_time），不画贯穿全图水平线
    - breakout 确认：confirm_mode(one_body / two_close)
    - pullback：回踩触边（edge zone）并保持不深度回归
    - continuation：回踩后在 continue_window_bars 内再次向突破方向收盘出界
    - 支持 historical（扫整个窗口）与 realtime（只返回最后一根产生的新事件）
    """
    out: List[Dict[str, Any]] = []
    if not bars:
        return out

    lb = int(lookback_bars)
    if len(bars) < lb:
        return out
    win = bars[-lb:]

    # ---- 参数兜底（更交易化）----
    atr14 = _atr14_from_bars(win) or 0.0
    threshold_buf = float(buffer)
    body_margin = max(threshold_buf, float(atr14) * 0.10)
    pb_margin = float(pullback_margin) if float(pullback_margin) > 0 else max(threshold_buf, float(atr14) * 0.15)

    # ---- 只保留 time-bounded zones ----
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
        """return ok, trigger_time, confirm_time"""
        if str(confirm_mode) == "two_close":
            n = max(2, int(confirm_n))
            if i - n + 1 < 0:
                return False, None, None
            for k in range(i - n + 1, i + 1):
                if not bull_close_outside(win[k], z):
                    return False, None, None
            return True, int(win[i - n + 1]["time"]), int(win[i]["time"])
        # one_body
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

    # ---- 状态机扫描（historical）----
    events: List[Dict[str, Any]] = []
    for z in norm_zones:
        # 每个 zone 最多出 1 个事件
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
                # 超时：没有 retest 则失效
                if brk_confirm_time is not None:
                    # 基于索引窗口限制
                    # brk_confirm_time 对应 i 的 time，不直接反查索引；用 “从突破确认开始计数”更直观
                    pass
                # 找 retest（在 breakout 确认后的窗口内）
                if brk_confirm_time is not None and t < int(brk_confirm_time):
                    continue
                # 只在确认后 retest_window 内寻找（按 bar 数）
                # 这里用索引差而不是时间差
                # 找到 breakout_confirm_idx
                # 为简单起见：当进入 BROKEN 时，i 已是 breakout confirm idx 或之后，所以用一个计数器
                # 采用：突破确认后的第一个可检测 bar 起开始递增
                # 用 i_window_from_confirm = i - i_confirm
                # 我们需要 i_confirm：可用 brk_confirm_time 在 win 内反查一次
                # 为避免每次 O(n)，提前一次性反查
                # ----
                # 这里实现：进入 BROKEN 后第一次运行时缓存 confirm_idx
                if "_confirm_idx" not in z:
                    # 反查（只会做一次）
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
                        # 事件视角：zone 到确认结束（不会延伸到最新）
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

    # ---- realtime: 只返回“最后一根产生的新事件” ----
    if str(scan_mode) == "realtime":
        t_last = int(win[-1]["time"])
        for e in events:
            ct = ((e.get("evidence") or {}).get("continuation") or {}).get("continue_time")
            if int(ct or 0) == t_last:
                out.append(e)
                if len(out) >= int(max_events):
                    break
        return out[: int(max_events)]

    # historical: 返回所有事件（时间排序）
    events.sort(key=lambda x: int((((x.get("evidence") or {}).get("continuation") or {}).get("continue_time") or 0)))
    return events[: int(max_events)]


def detect_false_breakout(
    bars: List[Dict[str, Any]],
    *,
    levels: List[Dict[str, Any]],
    zones: List[Dict[str, Any]],
    lookback_bars: int = 120,
    buffer: float = 0.0,
) -> List[Dict[str, Any]]:
    """
    False/Failed Breakout（无状态版）：
    - 向上假突破：high > top+buffer 且 close < top-buffer
    - 向下假突破：low < bottom-buffer 且 close > bottom+buffer
    """
    out: List[Dict[str, Any]] = []
    if len(bars) < int(lookback_bars):
        return out
    win = bars[-int(lookback_bars) :]

    candidates: List[Tuple[str, float, float]] = []
    for z in zones:
        try:
            center = float(z.get("center"))
            half = float(z.get("half_width_pips") or 0.0)
        except Exception:
            continue
        candidates.append((f"zone@{center}", center + half, center - half))
    for lv in levels:
        try:
            p = float(lv.get("price"))
        except Exception:
            continue
        candidates.append((f"level@{p}", p, p))
    if not candidates:
        return out

    for key, top, bot in candidates[:30]:
        # scan last to first, pick nearest signal
        for i in range(len(win) - 1, 0, -1):
            h = float(win[i]["high"])
            l = float(win[i]["low"])
            c = float(win[i]["close"])
            t = int(win[i]["time"])
            if h > top + buffer and c < top - buffer:
                out.append(
                    {
                        "id": "false_breakout_up",
                        "type": "false_breakout",
                        "direction": "Bearish",
                        "strength": "Medium",
                        "score": 75.0,
                        "evidence": {"key": key, "level": top, "bar_time": t, "bar_idx": i, "buffer": buffer, "high": h, "close": c},
                    }
                )
                return out[:8]
            if l < bot - buffer and c > bot + buffer:
                out.append(
                    {
                        "id": "false_breakout_down",
                        "type": "false_breakout",
                        "direction": "Bullish",
                        "strength": "Medium",
                        "score": 75.0,
                        "evidence": {"key": key, "level": bot, "bar_time": t, "bar_idx": i, "buffer": buffer, "low": l, "close": c},
                    }
                )
                return out[:8]
    return out[:8]


def detect_liquidity_sweep(
    bars: List[Dict[str, Any]],
    *,
    levels: List[Dict[str, Any]],
    lookback_bars: int = 160,
    buffer: float = 0.0,
    recover_within_bars: int = 3,
) -> List[Dict[str, Any]]:
    """
    Liquidity Sweep / Stop Run（无状态版）：
    - 扫高：high > level+buf，且在 recover_within_bars 内 close < level-buf
    - 扫低：low < level-buf，且在 recover_within_bars 内 close > level+buf
    """
    out: List[Dict[str, Any]] = []
    if len(bars) < int(lookback_bars):
        return out
    win = bars[-int(lookback_bars) :]

    # candidate levels: prefer swing_high/low kinds if available
    cand: List[Tuple[str, float]] = []
    for lv in levels:
        try:
            p = float(lv.get("price"))
        except Exception:
            continue
        kind = str(lv.get("kind") or "level")
        cand.append((f"{kind}@{p}", p))
    if not cand:
        return out

    for key, level in cand[:40]:
        # find sweep bar (recent first)
        for i in range(len(win) - 1, 0, -1):
            h = float(win[i]["high"])
            l = float(win[i]["low"])
            t = int(win[i]["time"])
            # sweep up
            if h > level + buffer:
                for j in range(i, min(len(win), i + 1 + int(recover_within_bars))):
                    c = float(win[j]["close"])
                    if c < level - buffer:
                        out.append(
                            {
                                "id": "liquidity_sweep_up_recover",
                                "type": "liquidity_sweep",
                                "direction": "Bearish",
                                "strength": "Strong" if j > i else "Medium",
                                "score": 82.0,
                                "evidence": {"key": key, "level": level, "sweep_time": t, "sweep_idx": i, "recover_time": int(win[j]["time"]), "recover_idx": j, "buffer": buffer},
                            }
                        )
                        return out[:8]
            # sweep down
            if l < level - buffer:
                for j in range(i, min(len(win), i + 1 + int(recover_within_bars))):
                    c = float(win[j]["close"])
                    if c > level + buffer:
                        out.append(
                            {
                                "id": "liquidity_sweep_down_recover",
                                "type": "liquidity_sweep",
                                "direction": "Bullish",
                                "strength": "Strong" if j > i else "Medium",
                                "score": 82.0,
                                "evidence": {"key": key, "level": level, "sweep_time": t, "sweep_idx": i, "recover_time": int(win[j]["time"]), "recover_idx": j, "buffer": buffer},
                            }
                        )
                        return out[:8]

    return out[:8]


def detect_bos_choch(
    bars: List[Dict[str, Any]],
    *,
    lookback_bars: int = 220,
    pivot_left: int = 3,
    pivot_right: int = 3,
    buffer: float = 0.0,
) -> List[Dict[str, Any]]:
    """
    BOS / CHOCH（deterministic swing-based）：
    - 用 fractal swings 推断结构（HH_HL/LH_LL）
    - structure_high/low 使用“确认结构点”
    - BOS：顺趋势突破结构点
    - CHOCH：逆趋势突破结构点
    """
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
    # fallback：若“确认结构点”不存在，则退化为最近 swing high/low
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
        # bullish trend
        if sh is not None and c > float(sh) + buffer:
            out.append({"id": "bos_up", "type": "bos", "direction": "Bullish", "strength": "Medium", "score": 78.0, "evidence": {"structure": structure, "level": float(sh), "bar_time": t, "close": c, "buffer": buffer}})
        if sl is not None and c < float(sl) - buffer:
            out.append({"id": "choch_down", "type": "choch", "direction": "Bearish", "strength": "Strong", "score": 85.0, "evidence": {"structure": structure, "level": float(sl), "bar_time": t, "close": c, "buffer": buffer}})
    elif structure == "LH_LL":
        # bearish trend
        if sl is not None and c < float(sl) - buffer:
            out.append({"id": "bos_down", "type": "bos", "direction": "Bearish", "strength": "Medium", "score": 78.0, "evidence": {"structure": structure, "level": float(sl), "bar_time": t, "close": c, "buffer": buffer}})
        if sh is not None and c > float(sh) + buffer:
            out.append({"id": "choch_up", "type": "choch", "direction": "Bullish", "strength": "Strong", "score": 85.0, "evidence": {"structure": structure, "level": float(sh), "bar_time": t, "close": c, "buffer": buffer}})
    else:
        # consolidation：仍可作为“结构突破”信号（弱 BOS），用于 scan/filter
        if sh is not None and c > float(sh) + buffer:
            out.append({"id": "bos_up", "type": "bos", "direction": "Bullish", "strength": "Weak", "score": 70.0, "evidence": {"structure": structure, "level": float(sh), "bar_time": t, "close": c, "buffer": buffer}})
        elif sl is not None and c < float(sl) - buffer:
            out.append({"id": "bos_down", "type": "bos", "direction": "Bearish", "strength": "Weak", "score": 70.0, "evidence": {"structure": structure, "level": float(sl), "bar_time": t, "close": c, "buffer": buffer}})

    return out[:8]

def tool_pattern_detect_batch(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    payload:
      - bars_by_tf: {tf:[bars]}
      - detectors: [PatternDetector dicts]
      - structures?: {levels:[], zones:[]}
      - indicator_series?: {id:{...}} (可选，后续用于 ATR ref 等)

    returns:
      - pattern_pack: {items:[...], summary:{...}}
    """
    bars_by_tf = payload.get("bars_by_tf") if isinstance(payload.get("bars_by_tf"), dict) else {}
    detectors = payload.get("detectors") if isinstance(payload.get("detectors"), list) else []
    structures = payload.get("structures") if isinstance(payload.get("structures"), dict) else None
    if not structures:
        # 兼容 IR executor：compile_v2_to_ir 可能会以 levels/zones 顶层输入传入
        lv_in = payload.get("levels") if isinstance(payload.get("levels"), list) else []
        zn_in = payload.get("zones") if isinstance(payload.get("zones"), list) else []
        structures = {"levels": lv_in, "zones": zn_in}
    levels, zones = _levels_and_zones(structures.get("levels"), structures.get("zones"))

    items: List[Dict[str, Any]] = []

    for d in detectors:
        if not isinstance(d, dict):
            continue
        t = str(d.get("type") or "")
        tf = str(d.get("timeframe") or "30m")
        bars = _bars_for_tf(bars_by_tf, tf)
        if not bars:
            continue

        if t == "rectangle_range":
            emit = str(d.get("emit") or "best")
            rep = detect_rectangle_ranges(
                bars,
                lookback_bars=int(d.get("lookback_bars") or 120),
                min_touches_per_side=int(d.get("min_touches_per_side") or 2),
                tolerance_atr_mult=float(d.get("tolerance_atr_mult") or 0.25),
                min_containment=float(d.get("min_containment") or 0.80),
                max_height_atr=float(d.get("max_height_atr") or 8.0),
                max_drift_atr=float(d.get("max_drift_atr") or 3.0),
                max_efficiency=float(d.get("max_efficiency") or 0.45),
                emit=emit,
                max_results=int(d.get("max_results") or 50),
                distinct_no_overlap=bool(d.get("distinct_no_overlap") if d.get("distinct_no_overlap") is not None else True),
                dedup_iou=float(d.get("dedup_iou") or 0.55),
            )
            for it in (rep.get("items") or []) if isinstance(rep, dict) else []:
                if not isinstance(it, dict):
                    continue
                it["timeframe"] = tf
                # 透传“候选总数”，帮助前端显示“找到多少 / 输出多少”
                if isinstance(it.get("evidence"), dict) and isinstance(rep.get("candidates"), int):
                    it["evidence"]["candidates_total"] = int(rep["candidates"])
                    it["evidence"]["emit_mode"] = emit
                items.append(it)

        elif t == "close_outside_level_zone":
            close_buf = float(d.get("close_buffer") or 0.0)
            for it in detect_close_outside_level_zone(
                bars,
                levels=levels,
                zones=zones,
                close_buffer=close_buf,
                scan_mode=str(d.get("scan_mode") or "realtime"),
                lookback_bars=int(d.get("lookback_bars") or 300),
                confirm_mode=str(d.get("confirm_mode") or "one_body"),
                confirm_n=int(d.get("confirm_n") or 2),
                max_events=int(d.get("max_events") or 50),
            ):
                it["timeframe"] = tf
                items.append(it)

        elif t == "breakout_retest_hold":
            for it in detect_breakout_retest_hold(
                bars,
                levels=levels,
                zones=zones,
                scan_mode=str(d.get("scan_mode") or "realtime"),
                lookback_bars=int(d.get("lookback_bars") or 300),
                confirm_mode=str(d.get("confirm_mode") or "one_body"),
                confirm_n=int(d.get("confirm_n") or 2),
                retest_window_bars=int(d.get("retest_window_bars") or 16),
                continue_window_bars=int(d.get("continue_window_bars") or 8),
                buffer=float(d.get("buffer") or 0.0),
                pullback_margin=float(d.get("pullback_margin") or 0.0),
                max_events=int(d.get("max_events") or 50),
            ):
                it["timeframe"] = tf
                items.append(it)

        elif t == "candlestick":
            atr14 = _atr14_from_bars(bars) or 0.0
            pats = detect_candlestick_patterns(bars, atr14=atr14)
            # filter by requested patterns if provided
            allow = d.get("patterns") if isinstance(d.get("patterns"), list) else []
            if allow:
                pats = [p for p in pats if p.get("id") in set(map(str, allow))]
            for p in pats:
                p2 = dict(p)
                p2["type"] = "candlestick"
                p2["timeframe"] = tf
                items.append(p2)

        elif t == "false_breakout":
            buf = float(d.get("buffer") or 0.0)
            for it in detect_false_breakout(bars, levels=levels, zones=zones, lookback_bars=int(d.get("lookback_bars") or 120), buffer=buf):
                it["timeframe"] = tf
                items.append(it)

        elif t == "liquidity_sweep":
            buf = float(d.get("buffer") or 0.0)
            for it in detect_liquidity_sweep(
                bars,
                levels=levels,
                lookback_bars=int(d.get("lookback_bars") or 160),
                buffer=buf,
                recover_within_bars=int(d.get("recover_within_bars") or 3),
            ):
                it["timeframe"] = tf
                items.append(it)

        elif t in ("bos", "choch"):
            # 统一由 detect_bos_choch 产出两者
            buf = float(d.get("buffer") or 0.0)
            got = detect_bos_choch(
                bars,
                lookback_bars=int(d.get("lookback_bars") or 220),
                pivot_left=int(d.get("pivot_left") or 3),
                pivot_right=int(d.get("pivot_right") or 3),
                buffer=buf,
            )
            for it in got:
                if it.get("type") != t:
                    continue
                it["timeframe"] = tf
                items.append(it)

        # 其他 type：后续 phase2 再接

    summary = {"items": len(items), "types": sorted(list({str(i.get("type")) for i in items if i.get("type")}))}
    return {"pattern_pack": {"items": items, "summary": summary}}
