import json
from typing import Any, Dict, List
from backend.services.chart_scene.indicators import (
    calc_volume_profile,
    calc_raja_sr,
    calc_msb_zigzag,
    calc_trend_exhaustion,
    sma, ema, atr, rsi, macd, detect_swings, structure_state_from_swings, confirmed_structure_levels
)

def build_agent_context(bars: List[Dict[str, Any]]) -> str:
    """
    Builds a high-density, structured JSON context for the Agent to avoid token waste.
    """
    if not bars:
        return json.dumps({"error": "No bars data provided."})
        
    recent_bars = bars[-3:] # Only provide the last 3 bars exact details
    
    # Calculate basic indicators
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
        "MACD": macd(closes)
    }
    
    # Advanced Indicators
    vp = calc_volume_profile(bars)
    raja_zones = calc_raja_sr(bars)
    # Get the nearest support/resistance to current price
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
    
    # Swings
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
            "Structure_Low": struct_levels.get("structure_low")
        }
    }
    
    return json.dumps(context, indent=2)

def analyzer_tool_schemas() -> List[Dict[str, Any]]:
    """
    Returns OpenAI compatible tool schemas specifically for the Analyzer Agent.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": "get_market_context",
                "description": "Get high-density technical analysis context including Volume Profile, RajaSR Zones, Structure Breaks, and Trend Exhaustion.",
                "parameters": {"type": "object", "properties": {}}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "market_get_quote",
                "description": "获取最新报价（bid/ask/last/spread）。symbol 可选，默认当前图表 symbol。",
                "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}}},
            },
        },
    ]

def executor_tool_schemas() -> List[Dict[str, Any]]:
    """
    Returns OpenAI compatible tool schemas specifically for the Executor Agent.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": "execute_ui_action",
                "description": "Emit a JSON action to the frontend to draw lines, markers or update the chart.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["trendline", "marker", "hline", "box", "arrow"]},
                        "price": {"type": "number"},
                        "time": {"type": "integer", "description": "Unix timestamp in seconds. Used for marker and hline."},
                        "color": {"type": "string"},
                        "text": {"type": "string", "description": "Text for marker."},
                        "position": {"type": "string", "enum": ["aboveBar", "belowBar"], "description": "Position for marker."},
                        "shape": {"type": "string", "enum": ["circle", "arrowUp", "arrowDown", "square", "labelUp", "labelDown"], "description": "Shape for marker."},
                        "t1": {"type": "integer", "description": "Unix timestamp in seconds for trendline or arrow start point."},
                        "t2": {"type": "integer", "description": "Unix timestamp in seconds for trendline or arrow end point."},
                        "p1": {"type": "number", "description": "Price for trendline or arrow start point."},
                        "p2": {"type": "number", "description": "Price for trendline or arrow end point."}
                    },
                    "required": ["action"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "account_list_positions",
                "description": "获取当前持仓列表。symbol 可选，默认全部持仓。",
                "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}}},
            },
        }
    ]
