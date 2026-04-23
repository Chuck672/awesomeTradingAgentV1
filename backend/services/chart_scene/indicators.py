from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


def _to_series(x: List[float]) -> pd.Series:
    return pd.Series(x, dtype="float64")


def sma(values: List[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    return float(_to_series(values).rolling(period).mean().iloc[-1])


def ema(values: List[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    return float(_to_series(values).ewm(span=period, adjust=False).mean().iloc[-1])


def atr(high: List[float], low: List[float], close: List[float], period: int = 14) -> Optional[float]:
    if len(close) < period + 1:
        return None
    h = _to_series(high)
    l = _to_series(low)
    c = _to_series(close)
    prev_c = c.shift(1)
    tr = pd.concat([(h - l).abs(), (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    a = tr.rolling(period).mean().iloc[-1]
    return float(a) if pd.notna(a) else None


def rsi(values: List[float], period: int = 14) -> Optional[float]:
    if len(values) < period + 1:
        return None
    s = _to_series(values)
    delta = s.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / (loss.replace(0, np.nan))
    out = 100 - (100 / (1 + rs))
    v = out.iloc[-1]
    return float(v) if pd.notna(v) else None


def macd(values: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, Optional[float]]:
    if len(values) < slow + signal + 1:
        return {"macd": None, "signal": None, "hist": None}
    s = _to_series(values)
    fast_ema = s.ewm(span=fast, adjust=False).mean()
    slow_ema = s.ewm(span=slow, adjust=False).mean()
    m = fast_ema - slow_ema
    sig = m.ewm(span=signal, adjust=False).mean()
    hist = m - sig
    return {"macd": float(m.iloc[-1]), "signal": float(sig.iloc[-1]), "hist": float(hist.iloc[-1])}


def slope_direction(values: List[float], lookback: int = 10, flat_threshold: float = 1e-9) -> str:
    """
    仅用于“结论化”：Up/Down/Flat。lookback 过小会噪声大，默认10。
    """
    if len(values) < lookback + 1:
        return "Flat"
    a = float(values[-1])
    b = float(values[-(lookback + 1)])
    diff = a - b
    if abs(diff) <= flat_threshold:
        return "Flat"
    return "Up" if diff > 0 else "Down"


@dataclass
class SwingPoint:
    kind: str  # "H" or "L"
    price: float
    time: int


def detect_swings(bars: List[Dict[str, Any]], left: int = 2, right: int = 2, max_points: int = 10) -> List[SwingPoint]:
    """
    简易 fractal swing 检测（用于结构 HH/HL vs LH/LL）。
    只取最近若干点即可，避免噪音塞给 AI。
    """
    if len(bars) < left + right + 1:
        return []
    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]
    times = [int(b["time"]) for b in bars]
    out: List[SwingPoint] = []
    for i in range(left, len(bars) - right):
        h = highs[i]
        if h == max(highs[i - left : i + right + 1]):
            out.append(SwingPoint(kind="H", price=h, time=times[i]))
        l = lows[i]
        if l == min(lows[i - left : i + right + 1]):
            out.append(SwingPoint(kind="L", price=l, time=times[i]))
    # 默认只保留最近若干点（用于 UI/AI 场景避免噪音）
    try:
        mp = int(max_points)
    except Exception:
        mp = 10
    mp = max(1, mp)
    out = sorted(out, key=lambda x: x.time)[-mp:]
    return out


def structure_state_from_swings(swings: List[SwingPoint]) -> str:
    """
    基于最近 2 个高点 + 2 个低点给一个粗结论。
    """
    highs = [s for s in swings if s.kind == "H"]
    lows = [s for s in swings if s.kind == "L"]
    if len(highs) < 2 or len(lows) < 2:
        return "Consolidation"
    h1, h2 = highs[-2], highs[-1]
    l1, l2 = lows[-2], lows[-1]
    if h2.price > h1.price and l2.price > l1.price:
        return "HH_HL"
    if h2.price < h1.price and l2.price < l1.price:
        return "LH_LL"
    return "Consolidation"


def confirmed_structure_levels(swings: List[SwingPoint]) -> Dict[str, Optional[float]]:
    """
    “结构点”版本（用于 BOS/CHoCH）：
    - 结构高：最近一个“已被后续低点确认过”的 swing high（即 high 后面出现过 low）
    - 结构低：最近一个“已被后续高点确认过”的 swing low（即 low 后面出现过 high）
    这比直接取最后一个 high/low 更稳，符合“结构点确认”的直觉。
    """
    if not swings:
        return {"structure_high": None, "structure_low": None}

    highs = [s for s in swings if s.kind == "H"]
    lows = [s for s in swings if s.kind == "L"]
    structure_high: Optional[float] = None
    structure_low: Optional[float] = None

    # 最新 high，且其后存在 low
    low_times = [s.time for s in lows]
    for h in reversed(highs):
        if any(t > h.time for t in low_times):
            structure_high = float(h.price)
            break

    # 最新 low，且其后存在 high
    high_times = [s.time for s in highs]
    for l in reversed(lows):
        if any(t > l.time for t in high_times):
            structure_low = float(l.price)
            break

    return {"structure_high": structure_high, "structure_low": structure_low}

# ==========================================
# New Advanced Indicators (Ported from TS)
# ==========================================

def calc_volume_profile(bars: List[Dict[str, Any]], bins_count: int = 50, value_area_pct: float = 70.0) -> Optional[Dict[str, Any]]:
    if not bars:
        return None

    min_price = float('inf')
    max_price = float('-inf')
    total_vol = 0.0

    for b in bars:
        low = float(b["low"])
        high = float(b["high"])
        vol = float(b.get("tick_volume", b.get("volume", 0)))
        if low < min_price: min_price = low
        if high > max_price: max_price = high
        total_vol += vol

    if min_price == float('inf') or max_price == float('-inf') or min_price == max_price or total_vol == 0:
        return None

    epsilon = (max_price - min_price) * 0.000001
    bin_size = (max_price - min_price + epsilon) / bins_count
    
    bins = [{"yStart": min_price + i * bin_size, "yEnd": min_price + (i + 1) * bin_size, "totalVolume": 0.0} for i in range(bins_count)]

    for b in bars:
        low = float(b["low"])
        high = float(b["high"])
        close = float(b["close"])
        vol = float(b.get("tick_volume", b.get("volume", 0)))
        if vol == 0: continue

        rng = high - low
        if rng == 0:
            bin_idx = min(int((close - min_price) / bin_size), bins_count - 1)
            if 0 <= bin_idx < bins_count:
                bins[bin_idx]["totalVolume"] += vol
            continue

        for i in range(bins_count):
            overlap_start = max(low, bins[i]["yStart"])
            overlap_end = min(high, bins[i]["yEnd"])
            overlap = overlap_end - overlap_start
            if overlap > 0:
                ratio = overlap / rng
                bins[i]["totalVolume"] += vol * ratio

    max_vol = 0
    poc_index = 0
    for i in range(bins_count):
        if bins[i]["totalVolume"] > max_vol:
            max_vol = bins[i]["totalVolume"]
            poc_index = i

    target_va = total_vol * (value_area_pct / 100.0)
    current_va = bins[poc_index]["totalVolume"]

    up_idx = poc_index + 1
    down_idx = poc_index - 1

    while current_va < target_va and (up_idx < bins_count or down_idx >= 0):
        vol_up = bins[up_idx]["totalVolume"] if up_idx < bins_count else -1
        vol_down = bins[down_idx]["totalVolume"] if down_idx >= 0 else -1

        if vol_up > vol_down:
            current_va += vol_up
            up_idx += 1
        elif vol_down > vol_up:
            current_va += vol_down
            down_idx -= 1
        else:
            if up_idx < bins_count:
                current_va += vol_up
                up_idx += 1
            if down_idx >= 0 and current_va < target_va:
                current_va += vol_down
                down_idx -= 1

    return {
        "pocPrice": (bins[poc_index]["yStart"] + bins[poc_index]["yEnd"]) / 2,
        "pocVolume": max_vol,
        "valueAreaLow": bins[down_idx + 1]["yStart"] if down_idx >= 0 else bins[0]["yStart"],
        "valueAreaHigh": bins[up_idx - 1]["yEnd"] if up_idx < bins_count else bins[-1]["yEnd"]
    }

def calc_raja_sr(bars: List[Dict[str, Any]], lookback: int = 1000, pivot: int = 2, max_zones: int = 6) -> List[Dict[str, Any]]:
    # Advanced RajaSR (Trade Mode Logic ported from frontend)
    bars = bars[-lookback:]
    if len(bars) < 50:
        return []
        
    def get_median(xs):
        import math
        xs = [x for x in xs if not math.isnan(x)]
        if not xs: return 0.0
        return float(np.median(xs))

    recent_bars = bars[-200:]
    trs = []
    for b in recent_bars:
        h, l = float(b.get("high", 0)), float(b.get("low", 0))
        if h > 0 and l > 0 and h > l:
            trs.append(h - l)
            
    tr_med = max(get_median(trs), 1e-6)
    
    tol_tr_mult = 0.20
    margin_tr_mult = 0.06
    min_touches = 2
    
    tol = max(tr_med * tol_tr_mult, 1e-6)
    margin = max(tr_med * margin_tr_mult, 1e-6)
    wick_min = tr_med * 0.25

    highs, lows = [], []
    for b in bars:
        h, l = float(b.get("high", 0)), float(b.get("low", 0))
        if h <= 0 or l <= 0: continue
        o, c = float(b.get("open", 0)), float(b.get("close", 0))
        body_high = max(o, c)
        body_low = min(o, c)
        
        if h - body_high >= wick_min:
            highs.append({"time": b.get("time"), "level": body_high, "wick": h})
        if body_low - l >= wick_min:
            lows.append({"time": b.get("time"), "level": body_low, "wick": l})
            
    if len(highs) + len(lows) < 6:
        # find swings fallback
        highs, lows = [], []
        n = len(bars)
        if n >= pivot * 2 + 3:
            for i in range(pivot, n - pivot):
                b = bars[i]
                h, l = float(b.get("high", 0)), float(b.get("low", 0))
                if h <= 0 or l <= 0: continue
                
                left_high = max([float(x.get("high", 0)) for x in bars[i-pivot:i]])
                left_low = min([float(x.get("low", 0)) for x in bars[i-pivot:i]])
                right_high = max([float(x.get("high", 0)) for x in bars[i+1:i+1+pivot]])
                right_low = min([float(x.get("low", 0)) for x in bars[i+1:i+1+pivot]])
                
                o, c = float(b.get("open", 0)), float(b.get("close", 0))
                
                if h > left_high and h > right_high:
                    highs.append({"time": b.get("time"), "level": max(o, c), "wick": h})
                if l < left_low and l < right_low:
                    lows.append({"time": b.get("time"), "level": min(o, c), "wick": l})

    def cluster_points(pts, t):
        if not pts: return []
        pts = sorted(pts, key=lambda x: x["level"])
        clusters = []
        cur = [pts[0]]
        cur_center = pts[0]["level"]
        for p in pts[1:]:
            if abs(p["level"] - cur_center) <= t:
                cur.append(p)
                cur_center = sum(x["level"] for x in cur) / len(cur)
            else:
                clusters.append(cur)
                cur = [p]
                cur_center = p["level"]
        clusters.append(cur)
        return clusters

    res_clusters = cluster_points(highs, tol)
    sup_clusters = cluster_points(lows, tol)

    last_bar = bars[-1]
    last_t = last_bar.get("time")
    last_close = float(last_bar.get("close", 0))

    diffs = []
    recent_80 = bars[-80:]
    for i in range(len(recent_80)-1):
        try:
            d = int(recent_80[i+1]["time"]) - int(recent_80[i]["time"])
            if d > 0: diffs.append(d)
        except: pass
    bar_sec = max(int(get_median(diffs)) if diffs else 60, 1)
    lookback_n = len(bars)

    def zone_quality_metrics(bottom, top):
        wick_touch = 0
        body_overlap = 0
        close_inside = 0
        for b in bars:
            h, l = float(b.get("high", 0)), float(b.get("low", 0))
            o, c = float(b.get("open", 0)), float(b.get("close", 0))
            if h >= bottom and l <= top: wick_touch += 1
            body_low = min(o, c)
            body_high = max(o, c)
            if body_high >= bottom and body_low <= top: body_overlap += 1
            if bottom <= c <= top: close_inside += 1
        return wick_touch, body_overlap, close_inside

    def zone_from_cluster(cluster, side):
        if len(cluster) < min_touches: return None
        levels = [p["level"] for p in cluster]
        wicks = [p["wick"] for p in cluster]
        times = [p["time"] for p in cluster]
        
        base = get_median(levels)
        last_touch_time = max(times)
        
        if side == "resistance":
            bottom = base
            top = base + margin
            wick_excess = [max(0.0, w - base) for w in wicks]
        else:
            top = base
            bottom = base - margin
            wick_excess = [max(0.0, base - w) for w in wicks]
            
        avg_excess = sum(wick_excess) / len(wick_excess) if wick_excess else 0.0
        score = len(cluster) * (avg_excess / margin if margin > 0 else 1.0)
        
        dist = abs(base - last_close)
        score = score / (1.0 + dist / (tr_med * 10.0))
        
        return {
            "bottom": bottom,
            "top": top,
            "from_time": min(times),
            "to_time": last_t,
            "last_touch_time": last_touch_time,
            "touches": len(cluster),
            "score": score,
            "level": base,
            "avg_wick_excess": avg_excess,
            "type": side
        }

    resistance = [z for z in (zone_from_cluster(cl, "resistance") for cl in res_clusters) if z is not None]
    support = [z for z in (zone_from_cluster(cl, "support") for cl in sup_clusters) if z is not None]

    def merge_zones(zs):
        if not zs: return []
        sorted_by_score = sorted(zs, key=lambda x: x["score"], reverse=True)
        dedup = []
        min_distance = tol * 1.8
        for cur in sorted_by_score:
            too_close = False
            for ex in dedup:
                overlapping = (cur["top"] >= ex["bottom"]) and (cur["bottom"] <= ex["top"])
                level_close = abs(cur["level"] - ex["level"]) < min_distance
                if overlapping or level_close:
                    too_close = True
                    break
            if not too_close:
                dedup.append(cur)
        return sorted(dedup, key=lambda x: x["bottom"])

    all_cands = merge_zones(resistance + support)
    resistance = [z for z in all_cands if z["type"] == "resistance"]
    support = [z for z in all_cands if z["type"] == "support"]

    import math
    max_close_inside_ratio = 0.22
    max_body_overlap_ratio = 0.35
    dist_mult = 20.0
    half_life_bars = max(20.0, lookback_n * 0.75)
    min_sep = max(tol * 1.2, margin * 1.8)

    def trade_score(z, side):
        dist = abs(z["level"] - last_close)
        if dist > tr_med * dist_mult: return -1e9
        
        wick_t, body_o, close_i = zone_quality_metrics(z["bottom"], z["top"])
        close_ratio = close_i / max(1.0, lookback_n)
        body_ratio = body_o / max(1.0, lookback_n)
        
        if close_ratio > max_close_inside_ratio: return -1e9
        if body_ratio > max_body_overlap_ratio: return -1e9
        
        side_mult = 1.0
        if side == "resistance" and z["bottom"] < last_close - tol: side_mult = 0.65
        if side == "support" and z["top"] > last_close + tol: side_mult = 0.65
        
        clean = 1.0 / (1.0 + close_ratio * 3.0 + body_ratio * 1.5)
        age_bars = max(0.0, (int(last_t) - int(z["last_touch_time"])) / bar_sec)
        recency = math.exp(-age_bars / half_life_bars)
        distance = 1.0 / (1.0 + dist / (tr_med * 4.0))
        
        return z["score"] * clean * recency * distance * side_mult

    def pick_trade(zs, side):
        scored = []
        for z in zs:
            s = trade_score(z, side)
            if s > -1e8:
                z_copy = dict(z)
                z_copy["trade_score"] = s
                scored.append(z_copy)
                
        picked = []
        if scored:
            if side == "resistance":
                preferred = [z for z in scored if z["level"] >= last_close]
                fallback = [z for z in scored if z["level"] < last_close]
            else:
                preferred = [z for z in scored if z["level"] <= last_close]
                fallback = [z for z in scored if z["level"] > last_close]
                
            anchor_pool = preferred if preferred else fallback
            anchor_pool = sorted(anchor_pool, key=lambda x: abs(x["level"] - last_close))
            if anchor_pool:
                picked.append(anchor_pool[0])
                
        scored = sorted(scored, key=lambda x: x["trade_score"], reverse=True)
        for z in scored:
            if len(picked) >= max_zones: break
            if any(abs(z["level"] - p["level"]) < min_sep for p in picked): continue
            if z not in picked: picked.append(z)
            
        return sorted(picked, key=lambda x: x["level"])

    resistance = pick_trade(resistance, "resistance")
    support = pick_trade(support, "support")
    
    return resistance + support

def calc_msb_zigzag(bars: List[Dict[str, Any]], pivot_period: int = 5) -> Dict[str, Any]:
    # Extremely simplified MSB ZigZag returning basic structural breaks (BoS / ChoCh proxy)
    if len(bars) < pivot_period * 2 + 1:
        return {"lines": []}
        
    points = []
    lines = []
    
    def get_pivot(idx, is_high):
        if idx < pivot_period or idx >= len(bars) - pivot_period: return None
        val = float(bars[idx]["high"] if is_high else bars[idx]["low"])
        for i in range(1, pivot_period + 1):
            comp_val_prev = float(bars[idx - i]["high"] if is_high else bars[idx - i]["low"])
            comp_val_next = float(bars[idx + i]["high"] if is_high else bars[idx + i]["low"])
            if is_high and (comp_val_prev > val or comp_val_next > val): return None
            if not is_high and (comp_val_prev < val or comp_val_next < val): return None
        return val

    for i in range(pivot_period, len(bars) - pivot_period):
        h_piv = get_pivot(i, True)
        l_piv = get_pivot(i, False)
        
        if h_piv is not None:
            points.append({"time": bars[i]["time"], "value": h_piv, "type": "H", "index": i})
        if l_piv is not None:
            points.append({"time": bars[i]["time"], "value": l_piv, "type": "L", "index": i})
            
    # Very basic structure tracking
    ext_trend = "No Trend"
    maj_h = maj_l = None
    
    for i in range(len(points)):
        pt = points[i]
        if pt["type"] == "H": maj_h = pt["value"]
        elif pt["type"] == "L": maj_l = pt["value"]
        
        # Check next bars
        next_idx = points[i+1]["index"] if i < len(points)-1 else len(bars)-1
        for j in range(pt["index"], next_idx + 1):
            c = float(bars[j]["close"])
            if maj_h is not None and c > maj_h:
                if ext_trend in ["No Trend", "Up Trend"]:
                    lines.append({"type": "BoS Bull", "level": maj_h, "time": bars[j]["time"]})
                else:
                    lines.append({"type": "ChoCh Bull", "level": maj_h, "time": bars[j]["time"]})
                ext_trend = "Up Trend"
                maj_h = None # reset to avoid duplicate fires
            elif maj_l is not None and c < maj_l:
                if ext_trend in ["No Trend", "Down Trend"]:
                    lines.append({"type": "BoS Bear", "level": maj_l, "time": bars[j]["time"]})
                else:
                    lines.append({"type": "ChoCh Bear", "level": maj_l, "time": bars[j]["time"]})
                ext_trend = "Down Trend"
                maj_l = None

    return {"lines": lines[-10:]} # return only recent 10 structures

def calc_trend_exhaustion(bars: List[Dict[str, Any]], short_len: int = 21, short_smooth: int = 7, long_len: int = 112, long_smooth: int = 3, threshold: int = 20) -> Dict[str, bool]:
    # Returns if the current market is hitting a reversal triangle (ob_reversal or os_reversal)
    if len(bars) < max(short_len, long_len) + max(short_smooth, long_smooth):
        return {"is_overbought": False, "is_oversold": False, "ob_reversal": False, "os_reversal": False}
    
    def get_highest(idx, length):
        start = max(0, idx - length + 1)
        slice_bars = bars[start:idx+1]
        return max(float(b["high"]) for b in slice_bars)

    def get_lowest(idx, length):
        start = max(0, idx - length + 1)
        slice_bars = bars[start:idx+1]
        return min(float(b["low"]) for b in slice_bars)

    s_raw = []
    l_raw = []
    for i in range(len(bars)):
        c = float(bars[i]["close"])
        s_max = get_highest(i, short_len)
        s_min = get_lowest(i, short_len)
        s_val = -50.0 if s_max == s_min else 100 * (c - s_max) / (s_max - s_min)
        s_raw.append(s_val)

        l_max = get_highest(i, long_len)
        l_min = get_lowest(i, long_len)
        l_val = -50.0 if l_max == l_min else 100 * (c - l_max) / (l_max - l_min)
        l_raw.append(l_val)
        
    def calc_ema(src: List[float], length: int) -> List[float]:
        if length <= 1: return src
        alpha = 2 / (length + 1)
        res = []
        ema = None
        for val in src:
            if ema is None:
                ema = val
            else:
                ema = alpha * val + (1 - alpha) * ema
            res.append(ema)
        return res

    s_pr = calc_ema(s_raw, short_smooth)
    l_pr = calc_ema(l_raw, long_smooth)
    
    # We need to look at the last two bars to detect a reversal
    idx_curr = len(bars) - 1
    idx_prev = len(bars) - 2

    def is_ob(idx):
        return s_pr[idx] >= -threshold and l_pr[idx] >= -threshold

    def is_os(idx):
        return s_pr[idx] <= -100 + threshold and l_pr[idx] <= -100 + threshold

    curr_ob = is_ob(idx_curr)
    curr_os = is_os(idx_curr)
    
    prev_ob = is_ob(idx_prev)
    prev_os = is_os(idx_prev)

    ob_reversal = (not curr_ob) and prev_ob
    os_reversal = (not curr_os) and prev_os
    
    return {
        "is_overbought": curr_ob, 
        "is_oversold": curr_os,
        "ob_reversal": ob_reversal,
        "os_reversal": os_reversal
    }
