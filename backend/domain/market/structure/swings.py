from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class SwingPoint:
    kind: str
    price: float
    time: int


def detect_swings(bars: List[Dict[str, Any]], left: int = 2, right: int = 2, max_points: int = 10) -> List[SwingPoint]:
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
    try:
        mp = int(max_points)
    except Exception:
        mp = 10
    mp = max(1, mp)
    out = sorted(out, key=lambda x: x.time)[-mp:]
    return out


def structure_state_from_swings(swings: List[SwingPoint]) -> str:
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
    if not swings:
        return {"structure_high": None, "structure_low": None}

    highs = [s for s in swings if s.kind == "H"]
    lows = [s for s in swings if s.kind == "L"]
    structure_high: Optional[float] = None
    structure_low: Optional[float] = None

    low_times = [s.time for s in lows]
    for h in reversed(highs):
        if any(t > h.time for t in low_times):
            structure_high = float(h.price)
            break

    high_times = [s.time for s in highs]
    for l in reversed(lows):
        if any(t > l.time for t in high_times):
            structure_low = float(l.price)
            break

    return {"structure_high": structure_high, "structure_low": structure_low}

