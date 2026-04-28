import json
from typing import Any, Dict, List

from backend.domain.market.indicators.ta import atr, ema, macd, rsi, sma
from backend.domain.market.indicators.trend_exhaustion import calc_trend_exhaustion
from backend.domain.market.indicators.volume_profile import calc_volume_profile
from backend.domain.market.structure.msb import calc_msb_zigzag
from backend.domain.market.structure.raja_sr_calc import calc_raja_sr
from backend.domain.market.structure.swings import confirmed_structure_levels, detect_swings, structure_state_from_swings


def build_agent_context(bars: List[Dict[str, Any]]) -> str:
    """
    Builds a high-density, structured JSON context for the Agent to avoid token waste.
    """
    if not bars:
        return json.dumps({"error": "No bars data provided."})

    recent_bars = bars[-3:]

    closes = [float(b["close"]) for b in bars]
    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]

    curr_close = closes[-1]

    basic_inds = {
        "SMA_20": sma(closes, 20),
        "SMA_50": sma(closes, 50),
        "EMA_20": ema(closes, 20),
        "ATR_14": atr(highs, lows, closes, 14),
        "RSI_14": rsi(closes, 14),
        "MACD": macd(closes),
    }

    vp = calc_volume_profile(bars)
    raja_zones = calc_raja_sr(bars)

    nearest_res = None
    nearest_sup = None
    for z in raja_zones:
        if z["type"] == "resistance" and z["bottom"] >= curr_close:
            if not nearest_res or z["bottom"] < nearest_res["bottom"]:
                nearest_res = z
        elif z["type"] == "support" and z["top"] <= curr_close:
            if not nearest_sup or z["top"] > nearest_sup["top"]:
                nearest_sup = z

    struct_breaks = calc_msb_zigzag(bars)
    trend_exhaustion = calc_trend_exhaustion(bars)

    swings = detect_swings(bars)
    struct_state = structure_state_from_swings(swings)
    struct_levels = confirmed_structure_levels(swings)

    context = {
        "current_price": curr_close,
        "recent_bars": recent_bars,
        "basic_indicators": basic_inds,
        "advanced_indicators": {
            "VolumeProfile_POC": vp["pocPrice"] if vp else None,
            "VolumeProfile_VAL": vp["valueAreaLow"] if vp else None,
            "VolumeProfile_VAH": vp["valueAreaHigh"] if vp else None,
            "Trend_Exhaustion": trend_exhaustion,
            "Nearest_Resistance": nearest_res,
            "Nearest_Support": nearest_sup,
            "Recent_Structure_Breaks": struct_breaks["lines"][-3:] if struct_breaks.get("lines") else [],
            "Market_Structure": struct_state,
            "Structure_High": struct_levels.get("structure_high"),
            "Structure_Low": struct_levels.get("structure_low"),
        },
    }

    return json.dumps(context, indent=2)
