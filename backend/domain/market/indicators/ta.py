from __future__ import annotations

from typing import Any, Dict, List, Optional

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
    if len(values) < lookback + 1:
        return "Flat"
    a = float(values[-1])
    b = float(values[-(lookback + 1)])
    diff = a - b
    if abs(diff) <= flat_threshold:
        return "Flat"
    return "Up" if diff > 0 else "Down"
