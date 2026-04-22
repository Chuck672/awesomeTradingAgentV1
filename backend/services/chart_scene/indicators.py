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

def calc_raja_sr(bars: List[Dict[str, Any]], lookback: int = 400, pivot: int = 5, max_zones: int = 5) -> List[Dict[str, Any]]:
    # Simplified RajaSR (Support/Resistance clustering)
    bars = bars[-lookback:]
    if len(bars) < 50:
        return []
    
    trs = []
    for b in bars[-200:]:
        h, l = float(b["high"]), float(b["low"])
        if h > l: trs.append(h - l)
    
    if not trs: return []
    med_tr = float(np.median(trs))
    tol = max(med_tr * 0.5, 1e-6)
    wick_min = max(med_tr * 0.25, 1e-6)
    
    highs, lows = [], []
    for b in bars:
        h, l = float(b["high"]), float(b["low"])
        o, c = float(b["open"]), float(b["close"])
        body_high, body_low = max(o, c), min(o, c)
        
        if h - body_high >= wick_min:
            highs.append({"level": body_high, "wick": h, "time": b["time"]})
        if body_low - l >= wick_min:
            lows.append({"level": body_low, "wick": l, "time": b["time"]})
            
    def cluster_points(pts, tol):
        if not pts: return []
        pts = sorted(pts, key=lambda x: x["level"])
        clusters = []
        cur = [pts[0]]
        cur_center = pts[0]["level"]
        for p in pts[1:]:
            if abs(p["level"] - cur_center) <= tol:
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
    
    zones = []
    for cl in res_clusters:
        if len(cl) >= 3: # minTouches
            levels = [p["level"] for p in cl]
            wicks = [p["wick"] for p in cl]
            base = float(np.median(levels))
            ext = max(wicks)
            zones.append({"top": ext, "bottom": base, "type": "resistance", "touches": len(cl)})
            
    for cl in sup_clusters:
        if len(cl) >= 3:
            levels = [p["level"] for p in cl]
            wicks = [p["wick"] for p in cl]
            base = float(np.median(levels))
            ext = min(wicks)
            zones.append({"top": base, "bottom": ext, "type": "support", "touches": len(cl)})
            
    # Sort zones by number of touches (score) descending and limit to top N
    zones = sorted(zones, key=lambda z: z["touches"], reverse=True)
    return zones[:max_zones]

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

def calc_trend_exhaustion(bars: List[Dict[str, Any]], short_len: int = 10, long_len: int = 21, threshold: int = 20) -> Dict[str, bool]:
    # Returns if the current market is Overbought or Oversold based on Williams %R logic
    if not bars: return {"is_overbought": False, "is_oversold": False}
    
    def get_pr(idx, length):
        start = max(0, idx - length + 1)
        slice_bars = bars[start:idx+1]
        h = max(float(b["high"]) for b in slice_bars)
        l = min(float(b["low"]) for b in slice_bars)
        c = float(bars[idx]["close"])
        if h == l: return -50
        return 100 * (c - h) / (h - l)
        
    s_pr = get_pr(len(bars)-1, short_len)
    l_pr = get_pr(len(bars)-1, long_len)
    
    ob = s_pr >= -threshold and l_pr >= -threshold
    os = s_pr <= -100 + threshold and l_pr <= -100 + threshold
    
    return {"is_overbought": ob, "is_oversold": os}
