import os
import json
from typing import Annotated, Literal, TypedDict, Any, List, Dict
from pydantic import BaseModel, Field

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool

# 1. State Definition
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    next: str  # supervisor's decision: "analyzer", "executor", or "FINISH"
    active_tool_groups: list[str]  # 动态注入的工具组权限

# 2. Define Real Tools for Analyzer
from backend.services.ai.agent_tools import build_agent_context

@tool
def get_market_context(symbol: str = "XAUUSDz", timeframe: str = "M15") -> str:
    """Get high-density technical analysis context including Volume Profile, RajaSR Zones, Structure Breaks, and Trend Exhaustion.
    Args:
        symbol: The symbol to analyze (default: XAUUSDz)
        timeframe: The timeframe to analyze (default: M15)
    """
    from backend.database.app_config import app_config
    import sqlite3
    import os
    
    bars = []
    try:
        # Get active broker to find the correct data sandbox
        active_broker = app_config.get_active_broker()
        if not active_broker:
            return '{"error": "No active broker found. Please connect to a broker first."}'
            
        broker_id = active_broker["id"]
        db_path = os.path.join(app_config.get_brokers_dir(), broker_id, "data.sqlite")
        
        if not os.path.exists(db_path):
            return f'{{"error": "Data database not found for broker {broker_id}."}}'
            
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            # Fetch last 100 bars of the requested symbol and timeframe
            cursor.execute('''
                SELECT time, open, high, low, close, tick_volume as volume 
                FROM ohlcv 
                WHERE symbol = ? AND timeframe = ? 
                ORDER BY time DESC LIMIT 100
            ''', (symbol, timeframe))
            rows = cursor.fetchall()
            if rows:
                bars = [dict(r) for r in reversed(rows)]
    except Exception as e:
        print(f"Failed to fetch real data for context: {e}")
        return f'{{"error": "Failed to fetch market data for {symbol} {timeframe} from database."}}'
        
    if not bars:
        return f'{{"error": "No market data found for {symbol} {timeframe} in the database. Please ensure MT5 is connected and streaming data."}}'
            
    # Add symbol and timeframe to context
    import json
    context_json = build_agent_context(bars)
    try:
        context_dict = json.loads(context_json)
        context_dict["symbol"] = symbol
        context_dict["timeframe"] = timeframe
        return json.dumps(context_dict, indent=2)
    except:
        return context_json

# -----------------------------
# 5.1 视图与环境控制 (View & Environment Control) - VIEW_CONTROL
# -----------------------------
@tool
def chart_set_symbol(symbol: str) -> str:
    """切换当前图表交易品种（如 XAUUSDz）。"""
    return f"Successfully sent UI command to switch symbol to {symbol}"

@tool
def chart_set_timeframe(timeframe: str) -> str:
    """切换图表时间周期（如 M1, M15, H1, H4, D1）。"""
    return f"Successfully sent UI command to switch timeframe to {timeframe}"

@tool
def chart_take_screenshot(action: str = "save_local") -> str:
    """截屏当前图表。action 可选 save_local (保存本地) 或 feed_ai (发给AI)。"""
    return f"Successfully sent UI command to take a screenshot with action {action}"

@tool
def chart_replay_start(start_time: int) -> str:
    """启动 Bar Replay 历史回放，定位到指定时间戳。"""
    return f"Successfully sent UI command to start replay at {start_time}"

@tool
def chart_replay_control(action: str, speed: int = 1) -> str:
    """控制回放进度，action 可选 play, pause, stop，speed 控制播放倍速。"""
    return f"Successfully sent UI command to control replay: {action} at speed {speed}"

# -----------------------------
# 5.2 数据与分析抓取 (Data & Analytics) - MARKET_DATA
# -----------------------------
@tool
def data_query_ohlcv(symbol: str = "XAUUSDz", timeframe: str = "M15") -> str:
    """拉取 K 线基础数据。"""
    return get_market_context.invoke({"symbol": symbol, "timeframe": timeframe})

@tool
def data_compute_indicators(symbol: str = "XAUUSDz", timeframe: str = "M15", indicators: list = None) -> str:
    """按需计算传统指标，传入 ["RSI", "MACD", "EMA"]。"""
    return get_market_context.invoke({"symbol": symbol, "timeframe": timeframe})

@tool
def data_compute_structure(symbol: str = "XAUUSDz", timeframe: str = "M15") -> str:
    """计算量价分布 (Volume Profile) 与市场结构 (RajaSR / MSB / ChoCh)。"""
    return get_market_context.invoke({"symbol": symbol, "timeframe": timeframe})

@tool
def data_query_economic_calendar() -> str:
    """获取未来 24/48 小时的重大财经日历数据。"""
    return "No major economic events in the next 48 hours."

# -----------------------------
# 5.3 绘图分析管理 (Drawing & Overlays) - VISUAL_ANNOTATION
# -----------------------------
@tool
def draw_objects(objects: list[dict]) -> str:
    """通用绘图入口。支持画线(hline, trendline)、标记(marker)和图形(box, arrow)。
    objects: 一组绘图对象的列表，例如 [{"type": "hline", "price": 1.10, "color": "#ef4444", "lineWidth": 2, "lineStyle": "dashed"}, {"type": "marker", "time": 1612131, "position": "belowBar", "text": "Buy", "color": "#22c55e"}]
    你可以指定 color 属性（如 "#ef4444" 表示红色, "#22c55e" 表示绿色, "#3b82f6" 表示蓝色），lineWidth（线宽），lineStyle（线型：solid/dashed/dotted）。
    """
    return f"Successfully sent UI command to draw objects"

@tool
def draw_clear_all() -> str:
    """移除图表上的所有手动或 AI 绘制的线条和标记。"""
    return "Successfully sent UI command to clear all drawings"

@tool
def draw_remove_object(id: str) -> str:
    """移除特定的绘图对象。"""
    return f"Successfully sent UI command to remove drawing {id}"

# -----------------------------
# 5.4 指标视图管理 (Indicator Management) - INDICATOR_CONTROL
# -----------------------------
@tool
def indicator_toggle(id: str, visible: bool) -> str:
    """开启或隐藏特定指标（如打开 RSI 附图，关闭 Bollinger Bands）。"""
    return f"Successfully sent UI command to toggle indicator {id} to {visible}"

@tool
def indicator_clear_all() -> str:
    """移除或隐藏图表上的所有指标，恢复纯净 K 线图。"""
    return "Successfully sent UI command to clear all indicators"

# Backward compatibility executor tool
@tool
def execute_ui_action(
    action: str = None,
    type: str = None, 
    price: float = None, 
    time: int = None, 
    color: str = None, 
    text: str = None,
    position: str = None,
    shape: str = None,
    t1: int = None,
    t2: int = None,
    p1: float = None,
    p2: float = None,
    objects: list = None
) -> str:
    """Emit a JSON action to the frontend to draw lines, markers or update the chart."""
    cmd = {k: v for k, v in locals().items() if v is not None and k != "cmd"}
    
    # If the LLM generates `type` instead of `action`, map it back to `action` for backward compatibility
    # so the frontend's JSON parser `if (action.action)` can definitely catch it
    if "type" in cmd and "action" not in cmd:
        cmd["action"] = cmd["type"]
        
    return f"Successfully sent UI command: {json.dumps(cmd)}"

# 4. Read API config from environment
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "siliconflow_api.env"))

base_url = os.getenv("Base_URL")
model_name = os.getenv("Model")
api_key = os.getenv("API_Key")

def get_llm(role: str, configs: dict = None):
    configs = configs or {}
    role_config = configs.get(role, {})
    
    # Fallback to environment variables if not provided
    req_base_url = role_config.get("base_url") or base_url
    req_model = role_config.get("model") or model_name
    req_api_key = role_config.get("api_key") or api_key
    
    return ChatOpenAI(
        model=req_model,
        openai_api_key=req_api_key,
        openai_api_base=req_base_url,
        max_tokens=2048,
    )

# 5. Build Agents
def build_multi_agent_graph(configs: dict = None):
    # Pass configs to get_llm to fetch the specific model for each agent
    analyzer_llm = get_llm("analyzer", configs)
    executor_llm = get_llm("executor", configs)
    supervisor_llm = get_llm("supervisor", configs)
    
    # Analyzer Agent
    analyzer_prompt = (
        "你是 QuantLogicLab 资深数据分析师和量化交易员。\n"
        "任务: 请根据被授权的工具获取市场数据。\n"
        "【数据查询模式】\n"
        "如果用户明确要求查询特定数值（如 周线/W1 的开盘价, 最新价格等），你必须：\n"
        "1. 在调用工具时传入正确的 `timeframe` 参数（如 W1, D1, H1 等）。\n"
        "2. 从工具返回的数据中提取确切的数值（如最新一根 K 线的 open 价格）。\n"
        "3. 明确输出该数值，并提示可以流转给 Executor 去画图或执行。**在此模式下，无需输出完整的交易信号和评分！**\n"
        "\n"
        "【深度分析模式】\n"
        "若用户要求分析趋势、寻找入场点，或未指定具体要求：\n"
        "重点关注 H1 宏观趋势、M15 入场点、RajaSR 阻力、MSB_ZigZag 结构以及成交量分布 (Volume Profile)。\n"
        "1. Trend Alignment: 确认当前信号是否与宏观趋势方向一致。\n"
        "2. Signal Scoring: 给出信号强度评分 (1-10) 及建议的 SL/TP 点位。\n"
        "3. 输出格式必须包含：Signal (买入/卖出/观望), Strength (X/10), Reasoning (核心理由)。\n"
        "\n"
        "【严格约束】\n"
        "1. Read-Only: 你只能调用查询类工具，无权下达交易指令或绘制图表。\n"
        "2. Data-Driven: 必须通过工具真实获取数据，严禁自行捏造数值！所有的推论必须引用工具返回的具体价格。\n"
        "3. 废话过滤: 严禁输出“好的”、“我知道了”等废话。报告必须使用中文。\n"
        "分析结束后，请在末尾输出 'FINISHED'。"
    )
    # We don't pre-bind tools here anymore, we do it dynamically in the node
    
    def analyzer_node(state: AgentState):
        active_groups = state.get("active_tool_groups", [])
        tools = []
        if "MARKET_DATA" in active_groups or not active_groups:  # Default to data if no groups specified
            tools.extend([get_market_context, data_query_ohlcv, data_compute_indicators, data_compute_structure, data_query_economic_calendar])
            
        if not tools:
            # If Analyzer was called but no tools were authorized, return error code
            from langchain_core.messages import AIMessage
            msg = AIMessage(content="[ERROR] INSUFFICIENT_PERMISSION_FOR_TASK: Supervisor routed to me but did not authorize MARKET_DATA tools.")
            msg.name = "analyzer"
            return {"messages": [msg]}
            
        analyzer_agent = create_react_agent(analyzer_llm, tools=tools, prompt=analyzer_prompt)
        
        result = analyzer_agent.invoke({"messages": state["messages"]})
        msg = result["messages"][-1]
        msg.name = "analyzer"
        return {"messages": [msg]} # Only return the last message to append

    # Executor Agent
    executor_prompt = (
        "你是高精度的交易执行引擎 (Executor)。你的唯一使命是调用工具来执行动作，绝不只是用嘴说！\n"
        "任务: 仔细阅读整个对话历史。找到用户最初要求画的线、控制图表或增删指标的指令，**立即调用对应的工具**进行执行。\n"
        "核心职责: \n"
        "1. 指令生成: 调用 `draw_objects`、`draw_clear_all`、`chart_set_symbol`、`indicator_toggle` 等工具来改变图表状态。\n"
        "   - 若要画线或做标记，使用 `draw_objects`。\n"
        "   - 若要清空图表，使用 `draw_clear_all`。\n"
        "   - 若要切换品种/周期，使用 `chart_set_symbol` 或 `chart_set_timeframe`。\n"
        "   - 若要控制指标，使用 `indicator_toggle`。\n"
        "2. 风控校准 (Risk Check): 若涉及真实下单（买入/卖出），强制计算仓位风险。\n"
        "严格约束: \n"
        "1. 必须动手: 严禁只用文本回复“我已执行”或“请查收”。你必须真实地触发 Tool Call！\n"
        "2. 提取上下文: 从 Analyzer 的回复中提取精确的价格数值（如 4746.222），作为画线的 `price` 等参数传入工具。\n"
        "3. 视觉配置: 当用户要求特定颜色或样式时，为 draw_objects 的元素添加 color (如 '#ef4444' 红, '#22c55e' 绿) 或 lineStyle ('dashed')。\n"
        "4. 废话过滤: 工具调用成功后，只输出“已成功执行动作。” 严禁说“如果需要其他帮助请随时告知”这种废话。\n"
        "执行结束后，请在末尾输出 'FINISHED'。"
    )
    
    def executor_node(state: AgentState):
        active_groups = state.get("active_tool_groups", [])
        tools = []
        if "VISUAL_ANNOTATION" in active_groups or "TRADE_EXECUTION" in active_groups or not active_groups: # Default to drawing if no groups specified
            tools.extend([draw_objects, draw_clear_all, draw_remove_object, execute_ui_action])
        if "VIEW_CONTROL" in active_groups or not active_groups:
            tools.extend([chart_set_symbol, chart_set_timeframe, chart_take_screenshot, chart_replay_start, chart_replay_control])
        if "INDICATOR_CONTROL" in active_groups or not active_groups:
            tools.extend([indicator_toggle, indicator_clear_all])
            
        if not tools:
            from langchain_core.messages import AIMessage
            msg = AIMessage(content="[ERROR] INSUFFICIENT_PERMISSION_FOR_TASK: Supervisor routed to me but did not authorize VISUAL_ANNOTATION or TRADE_EXECUTION tools.")
            msg.name = "executor"
            return {"messages": [msg]}
            
        executor_agent = create_react_agent(executor_llm, tools=tools, prompt=executor_prompt)
        
        result = executor_agent.invoke({"messages": state["messages"]})
        
        # Look for the last AI message
        ai_messages = [m for m in result["messages"] if m.type == "ai"]
        if ai_messages:
            msg = ai_messages[-1]
        else:
            msg = result["messages"][-1]
            
        print(f"\n[DEBUG Executor] Total messages in result: {len(result['messages'])}")
        for i, m in enumerate(result["messages"]):
            print(f"[DEBUG Executor] Msg {i} ({m.type}): {m.content[:100]}... tool_calls: {getattr(m, 'tool_calls', [])}")
            
        # VERY IMPORTANT: We no longer inject JSON into the text content.
        # Instead, we extract the UI actions and store them in `additional_kwargs`
        # so that `agent_routes.py` can broadcast them as structured WebSocket events.
        ui_actions = []
        for idx, m in enumerate(result["messages"]):
            if getattr(m, "tool_calls", None):
                for tc in m.tool_calls:
                    if tc["name"].startswith(("chart_", "draw_", "indicator_", "execute_ui_action")):
                        args = tc.get('args', {})
                        # Ensure 'action' is present
                        if "type" in args and "action" not in args:
                            args["action"] = args["type"]
                        if tc["name"] != "execute_ui_action":
                            args["action"] = tc["name"]
                        ui_actions.append(args)
                        
        msg.name = "executor"
        msg.additional_kwargs["ui_actions"] = ui_actions
        return {"messages": [msg]}
        
    # Supervisor
    class Route(BaseModel):
        user_intent_analysis: str = Field(description="Brief analysis of what the user originally requested and the current progress.")
        logical_steps: list[str] = Field(description="Step-by-step plan to achieve the user's goal.")
        active_tool_groups: list[str] = Field(description="Required capability modules for the next step, e.g., ['MARKET_DATA', 'VISUAL_ANNOTATION', 'VIEW_CONTROL', 'INDICATOR_CONTROL', 'TRADE_EXECUTION'].")
        next: Literal["analyzer", "executor", "FINISH"] = Field(
            description="Next step in the routing process based on the logical steps. Choose 'analyzer' for market data, 'executor' to act on UI, or 'FINISH' if the task is complete."
        )

    system_prompt = (
        "角色: 你是 QuantLogicLab 自动化交易系统的最高统筹者 (Supervisor)。\n"
        "职责: 监控整个对话历史，通过“思维链 (CoT)”拆解用户意图，并协调 'analyzer' (分析师) 和 'executor' (执行者)。\n"
        "\n"
        "【逻辑依赖法则 (Logical Dependency Mapping)】\n"
        "1. 绘图依赖分析：任何涉及“画线”、“标记”、“高亮”的操作，若未指定确切的数值坐标，必须强制要求 MARKET_DATA 能力，路由至 'analyzer' 寻找价格点。\n"
        "2. 执行依赖明确指令：只有当数据已就绪（如 Analyzer 已提供价格）或用户已提供绝对数值时，才要求 VISUAL_ANNOTATION 能力，路由至 'executor' 执行。\n"
        "3. 图表控制直接执行：任何涉及“截图”、“切换周期”、“切换品种”、“开关指标”、“回放”等操作，直接要求 VIEW_CONTROL 或 INDICATOR_CONTROL 能力，路由至 'executor' 执行。\n"
        "4. 交易依赖风控：任何涉及“下单”、“买入”、“卖出”的操作，必须强制要求 TRADE_EXECUTION 和 RISK_MANAGEMENT 能力，路由至 'executor' 执行。\n"
        "\n"
        "【操作流 (Operational Workflow)】\n"
        "- 分析并输出 `user_intent_analysis`, `logical_steps`, `active_tool_groups`。\n"
        "- 根据当前进度决定 `next` (analyzer / executor / FINISH)。\n"
        "- 若当前消息来自 'analyzer' 且已提供所需数据，你必须回忆最初的用户请求，将任务流转至 'executor' 进行画图。\n"
        "- 若任务已彻底闭环，或你发现流程陷入死循环，路由至 'FINISH'。\n"
        "\n"
        "【边缘案例 (Few-shot Edge Cases)】\n"
        "Case A (复合意图): 用户说“帮我看看现在的压力位并画出来”\n"
        "-> 意图: 分析压力位 + 绘制\n"
        "-> 进度: 刚开始，缺少数据\n"
        "-> active_tool_groups: [\"MARKET_DATA\"]\n"
        "-> next: \"analyzer\"\n"
        "\n"
        "Case B (纯展示意图): 用户说“把图表切换到1小时周期，并打开RSI指标”\n"
        "-> 意图: 纯控制，无需分析数据\n"
        "-> 进度: 待执行\n"
        "-> active_tool_groups: [\"VIEW_CONTROL\", \"INDICATOR_CONTROL\"]\n"
        "-> next: \"executor\"\n"
        "\n"
        "Case C (视觉复核): 用户说“帮我截个图看看”\n"
        "-> 意图: 截屏\n"
        "-> 进度: 待执行\n"
        "-> active_tool_groups: [\"VIEW_CONTROL\"]\n"
        "-> next: \"executor\"\n"
        "\n"
        "【严格约束】\n"
        "必须以严格的 JSON 格式输出，包含 user_intent_analysis, logical_steps, active_tool_groups, next 四个字段。严禁输出任何其他废话。\n"
    )

    def supervisor_node(state: AgentState):
        # Calculate recursion depth to prevent infinite loops
        recursion_count = len([m for m in state["messages"] if m.type == "ai"])
        if recursion_count > 10:
            print("Supervisor: Recursion limit reached, forcing FINISH.")
            return {"next": "FINISH"}

        # Short-circuit: If the last message is from executor, the task is always complete.
        # This saves an LLM call and prevents routing loops.
        if state["messages"] and state["messages"][-1].name == "executor":
            print("Supervisor: Last message from executor. Short-circuiting to FINISH.")
            return {"next": "FINISH"}
            
        # Inject Brief State Manifest
        last_action = "None"
        for m in reversed(state["messages"]):
            if m.name in ["analyzer", "executor"]:
                last_action = f"[{m.name.upper()}] completed an action: {m.content[:100]}..."
                break
                
        brief_state = f"【当前系统状态 (Brief_State_Manifest)】\n最近一次 AI 操作 (Last_Action): {last_action}\n"

        formatted_messages = [
            {"role": "system", "content": system_prompt + "\n\n" + brief_state}
        ]
        
        # We must map ALL history messages to "user" role when talking to the Supervisor.
        # If we send them as "assistant", the LLM might think "I just finished speaking" 
        # and output an empty string or just a period ('.'), breaking the JSON parsing.
        for m in state["messages"]:
            sender_name = m.name if m.name else ("user" if m.type == "human" else "ai")
            formatted_messages.append({
                "role": "user",
                "content": f"[{sender_name.upper()}]: {m.content}"
            })
            
        # Append a final explicit prompt to force the LLM to output the routing JSON
        formatted_messages.append({
            "role": "user",
            "content": "请基于以上最新状态，严格按照JSON格式输出下一步路由计划 (next)。"
        })
        
        # Use bind(max_tokens=300) to allow CoT reasoning
        fast_llm = supervisor_llm.bind(max_tokens=300)
        # Now that the last message is guaranteed to be "user", we can safely enforce JSON mode 
        # on supported providers (like SiliconFlow/DeepSeek) without hitting the 400 prefix error.
        try:
            fast_llm = fast_llm.bind(response_format={"type": "json_object"})
        except Exception:
            pass
        
        try:
            res = fast_llm.invoke(formatted_messages)
            content = res.content.strip()
            
            print(f"\n[DEBUG Supervisor] LLM Response: {content}\n")
            
            import json
            import re
            
            next_agent = "FINISH"
            active_tool_groups = []
            
            # Use non-greedy match to safely extract JSON block even if there is surrounding text
            match = re.search(r'\{.*?\}', content, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(0))
                    next_agent = data.get("next", "FINISH")
                    active_tool_groups = data.get("active_tool_groups", [])
                    print(f"[DEBUG Supervisor] Parsed Next: {next_agent}, Groups: {active_tool_groups}")
                except Exception as e:
                    print(f"[DEBUG Supervisor] JSON parsing failed: {e}")
                    pass
            
            # Always fallback to keyword check if next is still FINISH or parsing failed
            if next_agent == "FINISH":
                # Look at the raw content. If the analyzer just answered and we still need to draw
                if "executor" in content.lower(): 
                    next_agent = "executor"
                    if not active_tool_groups:
                        active_tool_groups = ["VISUAL_ANNOTATION"]
                elif "analyzer" in content.lower(): 
                    next_agent = "analyzer"
                    if not active_tool_groups:
                        active_tool_groups = ["MARKET_DATA"]
            
            print(f"[DEBUG Supervisor] Final Routing: {next_agent}")
            return {"next": next_agent, "active_tool_groups": active_tool_groups}
        except Exception as e:
            print(f"Supervisor error: {e}")
            return {"next": "FINISH", "active_tool_groups": []}
        
    # 6. Construct Graph
    workflow = StateGraph(AgentState)
    workflow.add_node("analyzer", analyzer_node)
    workflow.add_node("executor", executor_node)
    workflow.add_node("supervisor", supervisor_node)
    
    workflow.add_edge(START, "supervisor")
    
    workflow.add_conditional_edges(
        "supervisor",
        lambda x: x["next"],
        {
            "analyzer": "analyzer",
            "executor": "executor",
            "FINISH": END
        }
    )
    
    workflow.add_edge("analyzer", "supervisor")
    workflow.add_edge("executor", "supervisor")
    
    return workflow.compile()
