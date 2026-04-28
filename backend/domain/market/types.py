from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, TypedDict


class Bar(TypedDict, total=False):
    time: int
    open: float
    high: float
    low: float
    close: float
    tick_volume: float
    volume: float


class Level(TypedDict, total=False):
    price: float
    kind: str
    time: int


class Zone(TypedDict, total=False):
    top: float
    bottom: float
    center: float
    half_width: float
    half_width_pips: float
    pip_size: float
    from_time: int
    to_time: int
    kind: str
    source_level: Dict[str, Any]


Direction = Literal["Bullish", "Bearish", "Neutral"]
Strength = Literal["Weak", "Medium", "Strong"]


class PatternEvent(TypedDict, total=False):
    id: str
    type: str
    direction: Direction
    strength: Strength
    score: float
    timeframe: str
    evidence: Dict[str, Any]


def bar_time(b: Dict[str, Any]) -> Optional[int]:
    t = b.get("time")
    try:
        return int(t) if t is not None else None
    except Exception:
        return None


def f(x: Any) -> Optional[float]:
    try:
        return float(x) if x is not None else None
    except Exception:
        return None


def build_bar_series(bars: List[Dict[str, Any]]) -> tuple[list[float], list[float], list[float], list[float]]:
    opens: list[float] = []
    highs: list[float] = []
    lows: list[float] = []
    closes: list[float] = []
    for b in bars:
        o = f(b.get("open"))
        h = f(b.get("high"))
        l = f(b.get("low"))
        c = f(b.get("close"))
        if o is None or h is None or l is None or c is None:
            continue
        opens.append(o)
        highs.append(h)
        lows.append(l)
        closes.append(c)
    return opens, highs, lows, closes
