from __future__ import annotations

import unittest
from typing import Any, Dict, List


def _bar(t: int, o: float, h: float, l: float, c: float) -> Dict[str, Any]:
    return {"time": t, "open": o, "high": h, "low": l, "close": c, "tick_volume": 100}


def _pad_flat(start_t: int, n: int, price: float = 100.0) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for i in range(n):
        out.append(_bar(start_t + i * 60, price, price + 0.2, price - 0.2, price))
    return out


class TestMarketPatterns(unittest.TestCase):
    def test_candlestick_patterns_engulf_and_pinbar(self) -> None:
        from backend.domain.market.patterns.candles import detect_candlestick_patterns

        bars = _pad_flat(0, 20, 100.0)
        bars.append(_bar(2000, 101.0, 101.2, 99.0, 99.5))
        bars.append(_bar(2060, 99.4, 102.0, 99.2, 101.6))

        out = detect_candlestick_patterns(bars, atr14=1.0)
        ids = {x.get("id") for x in out}
        self.assertIn("bullish_engulfing", ids)

        bars2 = _pad_flat(0, 20, 100.0)
        bars2.append(_bar(2000, 100.8, 101.0, 99.0, 100.95))
        out2 = detect_candlestick_patterns(bars2, atr14=1.0)
        ids2 = {x.get("id") for x in out2}
        self.assertIn("bullish_pinbar", ids2)

    def test_false_breakout_uses_zone_top_bottom_correctly(self) -> None:
        from backend.domain.market.patterns.breakouts import detect_false_breakout

        base = _pad_flat(0, 200, 100.0)
        base.append(_bar(12060, 100.0, 101.5, 99.8, 99.9))

        zones = [{"top": 101.0, "bottom": 100.5, "from_time": 0, "to_time": 999999, "kind": "test_zone"}]
        out = detect_false_breakout(base, levels=[], zones=zones, lookback_bars=120, buffer=0.0, buffer_atr_mult=0.0, include_raja_sr=False)
        self.assertTrue(out)
        self.assertEqual(out[0]["id"], "false_breakout_up")
        ev = out[0]["evidence"]
        self.assertAlmostEqual(float(ev["top"]), 101.0, places=9)
        self.assertAlmostEqual(float(ev["bottom"]), 100.5, places=9)

    def test_liquidity_sweep_recover_within_bars(self) -> None:
        from backend.domain.market.patterns.breakouts import detect_liquidity_sweep

        bars = _pad_flat(0, 200, 100.0)
        bars.append(_bar(12060, 100.0, 101.2, 99.9, 100.9))
        bars.append(_bar(12120, 100.8, 101.0, 99.5, 100.8))
        bars.append(_bar(12180, 100.7, 100.9, 99.4, 100.7))
        bars.append(_bar(12240, 100.6, 100.8, 99.0, 100.4))

        levels = [{"price": 101.0, "kind": "swing_high"}]
        out = detect_liquidity_sweep(bars, levels=levels, lookback_bars=160, buffer=0.0, buffer_atr_mult=0.0, recover_within_bars=3)
        self.assertTrue(out)
        self.assertEqual(out[0]["id"], "liquidity_sweep_up_recover")


if __name__ == "__main__":
    unittest.main()
