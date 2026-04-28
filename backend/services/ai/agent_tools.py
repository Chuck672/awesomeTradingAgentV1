from typing import Any, Dict, List

from backend.services.ai.agent_context_builder import build_agent_context
from backend.services.ai.event_context_builder import build_event_context

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

__all__ = ["build_agent_context", "build_event_context", "analyzer_tool_schemas", "executor_tool_schemas"]
