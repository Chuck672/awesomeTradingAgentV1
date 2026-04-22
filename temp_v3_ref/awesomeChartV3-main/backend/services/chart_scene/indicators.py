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
