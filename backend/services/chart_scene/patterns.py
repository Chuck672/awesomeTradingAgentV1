from __future__ import annotations

from typing import Any, Dict, List


def _range(b: Dict[str, Any]) -> float:
    return float(b["high"]) - float(b["low"])


def _body(b: Dict[str, Any]) -> float:
    return abs(float(b["close"]) - float(b["open"]))


def _upper_wick(b: Dict[str, Any]) -> float:
    return float(b["high"]) - max(float(b["open"]), float(b["close"]))


def _lower_wick(b: Dict[str, Any]) -> float:
    return min(float(b["open"]), float(b["close"])) - float(b["low"])


def detect_candlestick_patterns(
    bars: List[Dict[str, Any]],
    *,
    atr14: float = 0.0,
    min_body_atr: float = 0.1,
) -> List[Dict[str, Any]]:
    """
    轻量蜡烛形态识别（M1 适用），作为“弱证据”：
    - Bullish/Bearish Engulfing
    - Doji
    - Pinbar（Bullish/Bearish）
    - Inside Bar
    输出统一格式：
    {id, direction, strength, evidence}
    """
    if len(bars) < 2:
        return []

    last = bars[-1]
    prev = bars[-2]

    rng = _range(last)
    if rng <= 0:
        return []

    body = _body(last)
    prev_body = _body(prev)
    upper = _upper_wick(last)
    lower = _lower_wick(last)

    # 过滤：实体太小（对 M1 噪音很大）
    if atr14 > 0 and body < float(min_body_atr) * float(atr14):
        body_ok = False
    else:
        body_ok = True

    out: List[Dict[str, Any]] = []

    last_bull = float(last["close"]) > float(last["open"])
    last_bear = float(last["close"]) < float(last["open"])
    prev_bull = float(prev["close"]) > float(prev["open"])
    prev_bear = float(prev["close"]) < float(prev["open"])

    # Engulfing（使用实体范围）
    if body_ok and last_bull and prev_bear:
        if float(last["open"]) <= float(prev["close"]) and float(last["close"]) >= float(prev["open"]):
            out.append({"id": "bullish_engulfing", "direction": "Bullish", "strength": "Medium", "evidence": {"body": body, "prev_body": prev_body}})
    if body_ok and last_bear and prev_bull:
        if float(last["open"]) >= float(prev["close"]) and float(last["close"]) <= float(prev["open"]):
            out.append({"id": "bearish_engulfing", "direction": "Bearish", "strength": "Medium", "evidence": {"body": body, "prev_body": prev_body}})

    # Doji：实体占比很小
    if rng > 0 and (body / rng) <= 0.1:
        out.append({"id": "doji", "direction": "Neutral", "strength": "Weak", "evidence": {"body_ratio": body / rng}})

    # Inside Bar：当前完全在上一根范围内
    if float(last["high"]) <= float(prev["high"]) and float(last["low"]) >= float(prev["low"]):
        out.append({"id": "inside_bar", "direction": "Neutral", "strength": "Weak", "evidence": {"prev_high": float(prev["high"]), "prev_low": float(prev["low"])}})

    # Pinbar（强调影线占比）
    if rng > 0:
        close_to_high = (float(last["high"]) - float(last["close"])) / rng
        close_to_low = (float(last["close"]) - float(last["low"])) / rng

        if lower >= 2.0 * max(body, 1e-9) and (lower / rng) >= 0.55 and close_to_high <= 0.25:
            out.append({"id": "bullish_pinbar", "direction": "Bullish", "strength": "Weak", "evidence": {"lower_wick": lower, "body": body, "wick_ratio": lower / rng}})
        if upper >= 2.0 * max(body, 1e-9) and (upper / rng) >= 0.55 and close_to_low <= 0.25:
            out.append({"id": "bearish_pinbar", "direction": "Bearish", "strength": "Weak", "evidence": {"upper_wick": upper, "body": body, "wick_ratio": upper / rng}})

    return out[:8]

