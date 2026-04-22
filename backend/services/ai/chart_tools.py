from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple


def analyzer_tool_schemas() -> List[Dict[str, Any]]:
    """
    提供给 LLM 的 分析类 tool schema。
    负责技术分析与策略决策，仅分配查询类工具（获取K线、计算指标、查询支撑阻力等）。
    """
    return [
        {
            "type": "function",
            "function": {
                "name": "market_get_quote",
                "description": "获取最新报价（bid/ask/last/spread）。symbol 可选，默认当前图表 symbol。",
                "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "account_get_info",
                "description": "获取账户信息（balance/equity/margin/free_margin 等）。",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "account_list_positions",
                "description": "获取当前持仓列表。symbol 可选，默认全部持仓。",
                "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "account_list_orders",
                "description": "获取当前挂单列表。symbol 可选，默认全部挂单。",
                "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}}},
            },
        }
    ]

def executor_tool_schemas() -> List[Dict[str, Any]]:
    """
    提供给 LLM 的 执行类 tool schema。
    负责风控、画图与下单，仅分配动作类工具。
    """
    return [
        {
            "type": "function",
            "function": {
                "name": "chart_set_symbol",
                "description": "切换图表品种（symbol），如 EURUSD / XAUUSDz",
                "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "chart_set_timeframe",
                "description": "切换图表周期（timeframe）。允许：M1/M5/M15/M30/H1/H4/D1",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "timeframe": {
                            "type": "string",
                            "enum": ["M1", "M5", "M15", "M30", "H1", "H4", "D1"],
                        }
                    },
                    "required": ["timeframe"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "chart_set_range",
                "description": "设置回看范围（MVP：前端会转换为滚动到更早的时间点）。days 与 bars 二选一。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "days": {"type": "integer", "minimum": 1, "maximum": 365},
                        "bars": {"type": "integer", "minimum": 50, "maximum": 20000},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "chart_replay_from_range",
                "description": "从相对时间开始回放（MVP：前端执行）。days/bars 二选一；speed_multiplier 例如 8 表示 8x。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "days": {"type": "integer", "minimum": 1, "maximum": 365},
                        "bars": {"type": "integer", "minimum": 50, "maximum": 20000},
                        "speed_multiplier": {"type": "integer", "minimum": 1, "maximum": 20},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "chart_set_replay_speed",
                "description": "设置回放速度倍数（例如 8 表示 8x）。注意：这是倍数，不是毫秒。",
                "parameters": {
                    "type": "object",
                    "properties": {"speed_multiplier": {"type": "integer", "minimum": 1, "maximum": 20}},
                    "required": ["speed_multiplier"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "chart_play",
                "description": "开始播放回放（如果已在回放模式）。",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "chart_pause",
                "description": "暂停回放（如果正在播放）。",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "chart_stop_replay",
                "description": "停止回放并恢复为全量K线。",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "chart_next",
                "description": "回放下一根K线（step）。",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "chart_prev",
                "description": "回放上一根K线（step）。",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "chart_reset_view",
                "description": "重置视图到最近一段（类似初始加载视图）。",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "chart_clear_markers",
                "description": "清除 markers（trade/study）。scope=all 表示全部清除。",
                "parameters": {"type": "object", "properties": {"scope": {"type": "string", "enum": ["all"]}}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "chart_draw",
                "description": "按结构化指令绘制到图表（线/框/水平线/marker）。objects 数组；时间为 Unix 秒。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "objects": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "type": {"type": "string", "enum": ["hline", "trendline", "box", "marker"]},
                                    "time": {"type": "integer"},
                                    "price": {"type": "number"},
                                    "t1": {"type": "integer"},
                                    "p1": {"type": "number"},
                                    "t2": {"type": "integer"},
                                    "p2": {"type": "number"},
                                    "from_time": {"type": "integer"},
                                    "to_time": {"type": "integer"},
                                    "low": {"type": "number"},
                                    "high": {"type": "number"},
                                    "position": {"type": "string", "enum": ["aboveBar", "belowBar"]},
                                    "color": {"type": "string"},
                                    "text": {"type": "string"},
                                },
                            },
                        }
                    },
                    "required": ["objects"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "chart_toggle_indicator",
                "description": "显示/隐藏指标（支持：svp=SessionVP，vrvp=VolumeProfile，bubble=Bubble, mstm=MSTM）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "enum": ["svp", "vrvp", "bubble", "mstm"]},
                        "enabled": {"type": "boolean"},
                    },
                    "required": ["id", "enabled"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "chart_clear_all_indicators",
                "description": "关闭图表上的所有指标显示。",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "chart_scroll_to_time",
                "description": "滚动到指定时间（Unix 秒）。",
                "parameters": {"type": "object", "properties": {"time": {"type": "integer"}}, "required": ["time"]},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "chart_start_replay_at_time",
                "description": "从指定时间开始 bar replay（Unix 秒）。",
                "parameters": {"type": "object", "properties": {"time": {"type": "integer"}}, "required": ["time"]},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "chart_take_screenshot",
                "description": "触发截图（由前端执行）。",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "chart_clear_drawings",
                "description": "清除绘图（MVP：清除全部）。",
                "parameters": {"type": "object", "properties": {"scope": {"type": "string", "enum": ["all"]}}},
            },
        },
    ]

def tool_schemas() -> List[Dict[str, Any]]:
    """
    提供给 LLM 的 tool schema（OpenAI tools/function-calling 格式）。
    注意：这里既包含“图表动作”（由前端执行），也包含“查询类工具”（由后端执行后回喂给模型）。
    保留此方法以兼容旧版 AI Chat，返回所有合并工具。
    """
    return analyzer_tool_schemas() + executor_tool_schemas()


def system_prompt() -> str:
    return "\n".join(
        [
            "你是 awesomeChart 的图表助手。你的任务是把用户的自然语言意图，转换为一组可执行的“图表动作”（通过 tools 调用）。",
            "",
            "规则（必须遵守）：",
            "1) 你只能通过 tools 产生动作；不要输出任何代码；不要操作 DOM；不要编造不存在的功能。",
            "2) 当用户提出的需求超出工具能力时：尽可能用最接近的动作近似；否则回复说明做不到，并给出可用的替代动作。",
            "3) 输出应以 tool_calls 为主；content 可以简短说明你做了什么。",
            "4) 当用户问“最新价格/当前价/bid/ask/点差/报价”时：你必须先调用 market_get_quote 获取真实数值；在最终回复中必须用 1-2 句话给出结果（包含 symbol + bid/ask 或 last + spread）；如用户要求落图或你认为有帮助，可再调用 chart_draw 画一条当前价水平线。",
            "5) 当用户问“账户/资金/权益/保证金”时：调用 account_get_info；当用户问“持仓/仓位”时：调用 account_list_positions；当用户问“挂单/订单”时：调用 account_list_orders。",
            "6) symbol 参数规则：用户明确提到某个 symbol 就用该 symbol；否则使用当前图表 symbol（如果上下文提供）。",
            "",
            "当前支持：切换品种/周期/回看范围，开关指标（svp/vrvp/bubble），滚动到时间，开始回放，截图，清除绘图。",
            "",
            "重要：当用户提到“回放/回看播放/replay/速度/8x/倍速”等关键词时：",
            "- 如果用户给的是相对时间（如 1天前/5天前/200根K）：必须使用 chart_replay_from_range，并带上 speed_multiplier；如果用户说“播放/开始播放”，则必须确保最终会开始播放（建议直接用 chart_replay_from_range，因为前端会自动 setPlaying(true)）。",
            "- 如果用户给的是绝对时间（Unix 秒）：使用 chart_start_replay_at_time，然后（如有倍速）调用 chart_set_replay_speed，最后如果用户说“播放/开始播放”必须调用 chart_play。",
            "- 用户明确说“暂停”用 chart_pause；“停止回放”用 chart_stop_replay。",
        ]
    )


def parse_tool_calls(tool_calls: Any) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    将 OpenAI tool_calls 解析成前端可执行 actions。
    返回：(actions, warnings)
    """
    actions: List[Dict[str, Any]] = []
    warnings: List[str] = []

    if not tool_calls:
        return actions, warnings

    for tc in tool_calls:
        try:
            fn = (tc.get("function") or {}) if isinstance(tc, dict) else {}
            name = str(fn.get("name") or "")
            args_raw = fn.get("arguments") or "{}"
            args = json.loads(args_raw) if isinstance(args_raw, str) else (args_raw if isinstance(args_raw, dict) else {})

            # 查询类 tools：由后端执行并回喂给模型；这里不产生前端 actions，也不告警
            if name in ("market_get_quote", "account_get_info", "account_list_positions", "account_list_orders"):
                continue

            if name == "chart_set_symbol":
                actions.append({"type": name, "symbol": str(args.get("symbol") or "")})
            elif name == "chart_set_timeframe":
                actions.append({"type": name, "timeframe": str(args.get("timeframe") or "")})
            elif name == "chart_set_range":
                out: Dict[str, Any] = {"type": name}
                if args.get("days") is not None:
                    out["days"] = int(args.get("days"))
                if args.get("bars") is not None:
                    out["bars"] = int(args.get("bars"))
                actions.append(out)
            elif name == "chart_replay_from_range":
                out2: Dict[str, Any] = {"type": name}
                if args.get("days") is not None:
                    out2["days"] = int(args.get("days"))
                if args.get("bars") is not None:
                    out2["bars"] = int(args.get("bars"))
                if args.get("speed_multiplier") is not None:
                    out2["speed_multiplier"] = int(args.get("speed_multiplier"))
                actions.append(out2)
            elif name == "chart_set_replay_speed":
                actions.append({"type": name, "speed_multiplier": int(args.get("speed_multiplier") or 1)})
            elif name in ("chart_play", "chart_pause", "chart_stop_replay", "chart_next", "chart_prev", "chart_reset_view"):
                actions.append({"type": name})
            elif name == "chart_clear_markers":
                actions.append({"type": name, "scope": "all"})
            elif name == "chart_draw":
                objs = args.get("objects")
                if not isinstance(objs, list):
                    objs = []
                actions.append({"type": name, "objects": objs})
            elif name == "chart_toggle_indicator":
                actions.append({"type": name, "id": str(args.get("id")), "enabled": bool(args.get("enabled"))})
            elif name == "chart_clear_all_indicators":
                actions.append({"type": name})
            elif name == "chart_scroll_to_time":
                actions.append({"type": name, "time": int(args.get("time"))})
            elif name == "chart_start_replay_at_time":
                actions.append({"type": name, "time": int(args.get("time"))})
            elif name == "chart_take_screenshot":
                actions.append({"type": name})
            elif name == "chart_clear_drawings":
                actions.append({"type": name, "scope": "all"})
            else:
                warnings.append(f"unknown tool: {name}")
        except Exception as e:
            warnings.append(f"failed to parse tool_call: {e}")

    # 清理空参数
    for a in actions:
        if a.get("type") == "chart_set_symbol" and not a.get("symbol"):
            warnings.append("chart_set_symbol missing symbol")
        if a.get("type") == "chart_set_timeframe" and not a.get("timeframe"):
            warnings.append("chart_set_timeframe missing timeframe")
        elif a.get("type") == "chart_clear_drawings":
            pass
        elif a.get("type") == "chart_clear_all_indicators":
            pass
        elif a.get("type") == "chart_take_screenshot":
            pass

    return actions, warnings
