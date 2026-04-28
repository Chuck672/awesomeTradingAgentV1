from __future__ import annotations

from typing import Any, Dict, List


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
    """
    轻量蜡烛形态识别（M1 适用），作为“弱证据”：
    - Bullish/Bearish Engulfing
    - Doji
    - Pinbar（Bullish/Bearish）
    - Inside Bar
    输出统一格式：
    {id, direction, strength, evidence}
    """
    from backend.domain.market.patterns.candles import detect_candlestick_patterns as _impl

    return _impl(
        bars,
        atr14=atr14,
        min_body_atr=min_body_atr,
        min_range_atr=min_range_atr,
        engulf_body_ratio=engulf_body_ratio,
        doji_body_ratio=doji_body_ratio,
        pin_wick_body_ratio=pin_wick_body_ratio,
        pin_wick_range_ratio=pin_wick_range_ratio,
        pin_close_far_ratio=pin_close_far_ratio,
    )

