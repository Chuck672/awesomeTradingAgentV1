from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.domain.market.types import bar_time, f


def _atr_from_bars(bars: List[Dict[str, Any]], period: int = 14) -> Optional[float]:
    if len(bars) < period + 1:
        return None
    trs: List[float] = []
    for i in range(1, len(bars)):
        h = f(bars[i].get("high"))
        l = f(bars[i].get("low"))
        pc = f(bars[i - 1].get("close"))
        if h is None or l is None or pc is None:
            continue
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if len(trs) < period:
        return None
    tail = trs[-period:]
    return sum(tail) / max(1, len(tail))


def _rng(b: Dict[str, Any]) -> Optional[float]:
    h = f(b.get("high"))
    l = f(b.get("low"))
    if h is None or l is None:
        return None
    return h - l


def _body(b: Dict[str, Any]) -> Optional[float]:
    o = f(b.get("open"))
    c = f(b.get("close"))
    if o is None or c is None:
        return None
    return abs(c - o)


def _upper_wick(b: Dict[str, Any]) -> Optional[float]:
    h = f(b.get("high"))
    o = f(b.get("open"))
    c = f(b.get("close"))
    if h is None or o is None or c is None:
        return None
    return h - max(o, c)


def _lower_wick(b: Dict[str, Any]) -> Optional[float]:
    l = f(b.get("low"))
    o = f(b.get("open"))
    c = f(b.get("close"))
    if l is None or o is None or c is None:
        return None
    return min(o, c) - l


def detect_candlestick_patterns(
    bars: List[Dict[str, Any]],
    *,
    atr14: float = 0.0,
    min_body_atr: float = 0.1,
    min_range_atr: float = 0.15,
    engulf_body_ratio: float = 1.1,
    doji_body_ratio: float = 0.1,
    pin_wick_body_ratio: float = 2.0,
    pin_wick_range_ratio: float = 0.55,
    pin_close_far_ratio: float = 0.25,
) -> List[Dict[str, Any]]:
    if len(bars) < 2:
        return []

    last = bars[-1]
    prev = bars[-2]

    rng = _rng(last)
    body = _body(last)
    prev_body = _body(prev)
    upper = _upper_wick(last)
    lower = _lower_wick(last)
    if rng is None or body is None or prev_body is None or upper is None or lower is None or rng <= 0:
        return []

    atr = float(atr14) if float(atr14 or 0.0) > 0 else float(_atr_from_bars(bars) or 0.0)
    rng_ok = True
    if atr > 0 and float(min_range_atr) > 0:
        rng_ok = rng >= float(min_range_atr) * atr

    body_ok = True
    if atr > 0 and float(min_body_atr) > 0:
        body_ok = body >= float(min_body_atr) * atr

    o_last = f(last.get("open"))
    c_last = f(last.get("close"))
    o_prev = f(prev.get("open"))
    c_prev = f(prev.get("close"))
    if o_last is None or c_last is None or o_prev is None or c_prev is None:
        return []

    out: List[Dict[str, Any]] = []
    t_last = bar_time(last)

    last_bull = c_last > o_last
    last_bear = c_last < o_last
    prev_bull = c_prev > o_prev
    prev_bear = c_prev < o_prev

    if rng_ok and body_ok and last_bull and prev_bear:
        if o_last <= c_prev and c_last >= o_prev and body >= max(1e-12, prev_body) * float(engulf_body_ratio):
            out.append(
                {
                    "id": "bullish_engulfing",
                    "direction": "Bullish",
                    "strength": "Medium",
                    "evidence": {"time": t_last, "body": body, "prev_body": prev_body, "atr14": atr or None},
                }
            )

    if rng_ok and body_ok and last_bear and prev_bull:
        if o_last >= c_prev and c_last <= o_prev and body >= max(1e-12, prev_body) * float(engulf_body_ratio):
            out.append(
                {
                    "id": "bearish_engulfing",
                    "direction": "Bearish",
                    "strength": "Medium",
                    "evidence": {"time": t_last, "body": body, "prev_body": prev_body, "atr14": atr or None},
                }
            )

    body_ratio = body / rng
    if rng_ok and body_ratio <= float(doji_body_ratio):
        if atr <= 0 or body <= atr * max(0.12, float(min_body_atr) * 0.8):
            out.append({"id": "doji", "direction": "Neutral", "strength": "Weak", "evidence": {"time": t_last, "body_ratio": body_ratio, "atr14": atr or None}})

    prev_rng = _rng(prev)
    if prev_rng is not None and prev_rng > 0 and (atr <= 0 or prev_rng >= float(min_range_atr) * atr):
        h_last = f(last.get("high"))
        l_last = f(last.get("low"))
        h_prev = f(prev.get("high"))
        l_prev = f(prev.get("low"))
        if h_last is not None and l_last is not None and h_prev is not None and l_prev is not None:
            if h_last <= h_prev and l_last >= l_prev:
                out.append({"id": "inside_bar", "direction": "Neutral", "strength": "Weak", "evidence": {"time": t_last, "prev_high": h_prev, "prev_low": l_prev}})

    close_to_high = (f(last.get("high")) - c_last) / rng if f(last.get("high")) is not None else None
    close_to_low = (c_last - f(last.get("low"))) / rng if f(last.get("low")) is not None else None
    body_small = body <= rng * 0.35

    if rng_ok and body_small and close_to_high is not None and lower >= float(pin_wick_body_ratio) * max(body, 1e-12) and (lower / rng) >= float(pin_wick_range_ratio) and close_to_high <= float(pin_close_far_ratio):
        out.append({"id": "bullish_pinbar", "direction": "Bullish", "strength": "Weak", "evidence": {"time": t_last, "lower_wick": lower, "body": body, "wick_ratio": lower / rng, "atr14": atr or None}})

    if rng_ok and body_small and close_to_low is not None and upper >= float(pin_wick_body_ratio) * max(body, 1e-12) and (upper / rng) >= float(pin_wick_range_ratio) and close_to_low <= float(pin_close_far_ratio):
        out.append({"id": "bearish_pinbar", "direction": "Bearish", "strength": "Weak", "evidence": {"time": t_last, "upper_wick": upper, "body": body, "wick_ratio": upper / rng, "atr14": atr or None}})

    return out[:8]
