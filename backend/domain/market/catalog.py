from __future__ import annotations

from typing import Any, Dict, List


def get_market_feature_catalog() -> Dict[str, Any]:
    return {
        "version": "market_feature_catalog_v1",
        "groups": [
            {
                "id": "patterns",
                "label": "Patterns",
                "items": [
                    {
                        "id": "candlestick",
                        "label": "Candlestick Patterns",
                        "params": [
                            {"name": "min_body_atr", "type": "number", "default": 0.1, "min": 0.0, "max": 1.0},
                            {"name": "min_range_atr", "type": "number", "default": 0.15, "min": 0.0, "max": 5.0},
                            {"name": "engulf_body_ratio", "type": "number", "default": 1.1, "min": 1.0, "max": 5.0},
                            {"name": "doji_body_ratio", "type": "number", "default": 0.1, "min": 0.0, "max": 1.0},
                            {"name": "pin_wick_body_ratio", "type": "number", "default": 2.0, "min": 1.0, "max": 10.0},
                            {"name": "pin_wick_range_ratio", "type": "number", "default": 0.55, "min": 0.0, "max": 1.0},
                        ],
                        "outputs": ["bullish_engulfing", "bearish_engulfing", "doji", "inside_bar", "bullish_pinbar", "bearish_pinbar"],
                    },
                    {
                        "id": "liquidity_sweep",
                        "label": "Liquidity Sweep (Stop Run)",
                        "params": [
                            {"name": "lookback_bars", "type": "integer", "default": 160, "min": 10, "max": 5000},
                            {"name": "buffer", "type": "number", "default": 0.0, "min": 0.0, "max": 999999.0},
                            {"name": "buffer_atr_mult", "type": "number", "default": 0.05, "min": 0.0, "max": 1.0},
                            {"name": "recover_within_bars", "type": "integer", "default": 3, "min": 1, "max": 20},
                            {"name": "max_candidates", "type": "integer", "default": 40, "min": 1, "max": 200},
                        ],
                        "outputs": ["liquidity_sweep_up_recover", "liquidity_sweep_down_recover"],
                    },
                    {
                        "id": "false_breakout",
                        "label": "False Breakout (Failed Break)",
                        "params": [
                            {"name": "lookback_bars", "type": "integer", "default": 120, "min": 10, "max": 5000},
                            {"name": "buffer", "type": "number", "default": 0.0, "min": 0.0, "max": 999999.0},
                            {"name": "buffer_atr_mult", "type": "number", "default": 0.05, "min": 0.0, "max": 1.0},
                            {"name": "max_candidates", "type": "integer", "default": 30, "min": 1, "max": 200},
                            {"name": "include_raja_sr", "type": "boolean", "default": True},
                            {"name": "max_raja_zones", "type": "integer", "default": 6, "min": 0, "max": 20},
                        ],
                        "outputs": ["false_breakout_up", "false_breakout_down"],
                    },
                    {
                        "id": "rectangle_range",
                        "label": "Rectangle Range",
                        "params": [
                            {"name": "lookback_bars", "type": "integer", "default": 120, "min": 10, "max": 5000},
                            {"name": "min_touches_per_side", "type": "integer", "default": 2, "min": 1, "max": 20},
                            {"name": "tolerance_atr_mult", "type": "number", "default": 0.25, "min": 0.0, "max": 5.0},
                            {"name": "min_containment", "type": "number", "default": 0.80, "min": 0.0, "max": 1.0},
                            {"name": "max_height_atr", "type": "number", "default": 8.0, "min": 0.1, "max": 50.0},
                            {"name": "max_drift_atr", "type": "number", "default": 3.0, "min": 0.0, "max": 50.0},
                            {"name": "max_efficiency", "type": "number", "default": 0.45, "min": 0.0, "max": 1.0},
                            {"name": "emit", "type": "string", "default": "best", "enum": ["best", "distinct", "all"]},
                            {"name": "max_results", "type": "integer", "default": 50, "min": 1, "max": 500},
                            {"name": "distinct_no_overlap", "type": "boolean", "default": True},
                            {"name": "dedup_iou", "type": "number", "default": 0.55, "min": 0.0, "max": 1.0},
                        ],
                        "outputs": ["rectangle_range"],
                    },
                    {
                        "id": "close_outside_level_zone",
                        "label": "Close Outside Level Zone",
                        "params": [
                            {"name": "close_buffer", "type": "number", "default": 0.0, "min": 0.0, "max": 999999.0},
                            {"name": "scan_mode", "type": "string", "default": "realtime", "enum": ["realtime", "historical"]},
                            {"name": "lookback_bars", "type": "integer", "default": 300, "min": 10, "max": 10000},
                            {"name": "confirm_mode", "type": "string", "default": "one_body", "enum": ["one_body", "two_close"]},
                            {"name": "confirm_n", "type": "integer", "default": 2, "min": 2, "max": 10},
                            {"name": "max_events", "type": "integer", "default": 50, "min": 1, "max": 500},
                        ],
                        "outputs": ["close_outside_zone_up", "close_outside_zone_down"],
                    },
                    {
                        "id": "breakout_retest_hold",
                        "label": "Breakout Retest Hold",
                        "params": [
                            {"name": "scan_mode", "type": "string", "default": "realtime", "enum": ["realtime", "historical"]},
                            {"name": "lookback_bars", "type": "integer", "default": 300, "min": 10, "max": 10000},
                            {"name": "confirm_mode", "type": "string", "default": "one_body", "enum": ["one_body", "two_close"]},
                            {"name": "confirm_n", "type": "integer", "default": 2, "min": 2, "max": 10},
                            {"name": "retest_window_bars", "type": "integer", "default": 16, "min": 1, "max": 200},
                            {"name": "continue_window_bars", "type": "integer", "default": 8, "min": 1, "max": 200},
                            {"name": "buffer", "type": "number", "default": 0.0, "min": 0.0, "max": 999999.0},
                            {"name": "pullback_margin", "type": "number", "default": 0.0, "min": 0.0, "max": 999999.0},
                            {"name": "max_events", "type": "integer", "default": 50, "min": 1, "max": 500},
                        ],
                        "outputs": ["breakout_retest_hold_up", "breakout_retest_hold_down"],
                    },
                    {
                        "id": "bos_choch",
                        "label": "BOS / CHOCH",
                        "params": [
                            {"name": "lookback_bars", "type": "integer", "default": 220, "min": 10, "max": 5000},
                            {"name": "pivot_left", "type": "integer", "default": 3, "min": 1, "max": 20},
                            {"name": "pivot_right", "type": "integer", "default": 3, "min": 1, "max": 20},
                            {"name": "buffer", "type": "number", "default": 0.0, "min": 0.0, "max": 999999.0},
                        ],
                        "outputs": ["bos_up", "bos_down", "choch_up", "choch_down"],
                    },
                    {
                        "id": "raja_sr_touch",
                        "label": "RajaSR Zone Touch (Trigger)",
                        "params": [
                            {"name": "limit", "type": "integer", "default": 400, "min": 50, "max": 5000},
                            {"name": "max_zones", "type": "integer", "default": 5, "min": 1, "max": 20},
                        ],
                        "outputs": ["raja_sr_touch"],
                    },
                    {
                        "id": "msb_zigzag_break",
                        "label": "MSB ZigZag Break (Trigger)",
                        "params": [
                            {"name": "limit", "type": "integer", "default": 400, "min": 50, "max": 5000},
                            {"name": "detect_bos", "type": "boolean", "default": True},
                            {"name": "detect_choch", "type": "boolean", "default": True},
                        ],
                        "outputs": ["msb_zigzag_break"],
                    },
                    {
                        "id": "trend_exhaustion",
                        "label": "Trend Exhaustion (Trigger)",
                        "params": [
                            {"name": "limit", "type": "integer", "default": 400, "min": 50, "max": 5000},
                        ],
                        "outputs": ["trend_exhaustion"],
                    },
                ],
            },
            {
                "id": "structures",
                "label": "Structures",
                "items": [
                    {"id": "raja_sr_level_zone", "label": "RajaSR Level Zones", "params": [{"name": "lookback", "type": "integer", "default": 1000}], "outputs": ["support_zones", "resistance_zones"]},
                    {"id": "swings", "label": "Fractal Swings", "params": [{"name": "left", "type": "integer", "default": 2}, {"name": "right", "type": "integer", "default": 2}, {"name": "max_points", "type": "integer", "default": 10}], "outputs": ["swing_points"]},
                    {"id": "msb_zigzag", "label": "MSB ZigZag", "params": [{"name": "pivot_period", "type": "integer", "default": 5}], "outputs": ["bos", "choch", "lines"]},
                ],
            },
            {
                "id": "indicators",
                "label": "Indicators",
                "items": [
                    {"id": "atr", "label": "ATR", "params": [{"name": "period", "type": "integer", "default": 14}], "outputs": ["ATR_14"]},
                    {"id": "rsi", "label": "RSI", "params": [{"name": "period", "type": "integer", "default": 14}], "outputs": ["RSI_14"]},
                    {"id": "macd", "label": "MACD", "params": [{"name": "fast", "type": "integer", "default": 12}, {"name": "slow", "type": "integer", "default": 26}, {"name": "signal", "type": "integer", "default": 9}], "outputs": ["MACD"]},
                    {"id": "ema", "label": "EMA", "params": [{"name": "period", "type": "integer", "default": 20}], "outputs": ["EMA_20"]},
                    {"id": "sma", "label": "SMA", "params": [{"name": "periods", "type": "array", "default": [20, 50]}], "outputs": ["SMA_20", "SMA_50"]},
                    {"id": "volume_profile", "label": "Volume Profile", "params": [{"name": "bins_count", "type": "integer", "default": 50}, {"name": "value_area_pct", "type": "number", "default": 70.0}], "outputs": ["POC", "VAH", "VAL"]},
                    {"id": "trend_exhaustion", "label": "Trend Exhaustion", "params": [{"name": "short_len", "type": "integer", "default": 21}, {"name": "short_smooth", "type": "integer", "default": 7}, {"name": "long_len", "type": "integer", "default": 112}, {"name": "long_smooth", "type": "integer", "default": 3}, {"name": "threshold", "type": "number", "default": 20}], "outputs": ["Trend_Exhaustion"]},
                ],
            },
        ],
    }


def list_feature_ids() -> List[str]:
    cat = get_market_feature_catalog()
    out: List[str] = []
    for g in cat.get("groups") or []:
        for it in (g.get("items") or []):
            fid = it.get("id")
            if isinstance(fid, str) and fid:
                out.append(fid)
    return sorted(set(out))
