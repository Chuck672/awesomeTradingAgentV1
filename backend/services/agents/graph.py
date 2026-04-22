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

# 3. Define Real Tools for Executor
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
        "你是 QuantLogicLab 资深量化交易员，专注于多周期技术分析。\n"
        "任务: 请调用 `get_market_context` 工具获取市场数据（仅调用一次）。重点关注 H1 宏观趋势、M15 入场点、RajaSR 阻力、MSB_ZigZag 结构以及成交量分布 (Volume Profile)。\n"
        "分析指南: \n"
        "1. Trend Alignment: 确认 M15 信号是否与 H1 趋势方向一致。\n"
        "2. Signal Scoring: 给出信号强度评分 (1-10) 及建议的 SL/TP 点位。\n"
        "3. Contextual Filter: 过滤掉得分较低的弱 RajaSR 区域。\n"
        "严格约束: \n"
        "1. Read-Only: 你只能调用查询类工具，无权下达交易指令或绘制图表。\n"
        "2. Data-Driven: 所有的推论必须引用工具返回的具体价格或指标数值。\n"
        "3. 语言限制: 你的最终分析报告必须使用中文 (简体中文) 输出！但保留专业的英文交易术语 (如 EMS, RSI, MACD, ChoCh, POC, VAL, VAH, Support, Resistance)。\n"
        "4. 废话过滤: 严禁输出“好的”、“我知道了”等任何礼貌性废话。\n"
        "输出格式: 以中文总结结论，包含：Signal (买入/卖出/观望), Strength (X/10), Reasoning (核心理由)。\n"
        "分析结束后，请在末尾输出 'FINISHED'。"
    )
    analyzer_agent = create_react_agent(analyzer_llm, tools=[get_market_context], prompt=analyzer_prompt)
    
    def analyzer_node(state: AgentState):
        # We pass the messages to the agent, it runs until it decides it's done
        result = analyzer_agent.invoke({"messages": state["messages"]})
        msg = result["messages"][-1]
        msg.name = "analyzer"
        return {"messages": [msg]} # Only return the last message to append

    # Executor Agent
    executor_prompt = (
        "你是高精度的交易执行引擎，负责将 Analyzer 的决策转化为具体的 UI 指令或 MT5 订单。\n"
        "任务: 基于 Analyzer 提供的分析，调用 `execute_ui_action` 工具（仅调用一次）执行绘制标记等动作。\n"
        "核心职责: \n"
        "1. 风控校准 (Risk Check): 强制计算当前仓位风险。若不满足风控比例 (如大于 2%)，必须输出 {'error': 'risk_overflow'} 拒绝执行。\n"
        "2. 指令生成: 生成符合标准 JSON 规范的 UI_Action 指令，用于前端图表渲染。\n"
        "   - 若要画水平线，请设置 action='hline', price=数值。\n"
        "   - 若要画图标(如 Buy/Sell)，请设置 action='marker', time=K线时间戳, position='belowBar'(买)/'aboveBar'(卖), shape='arrowUp'(买)/'arrowDown'(卖), text='Buy'/'Sell', color='#00bfa5'(买)/'#ff4444'(卖)。\n"
        "   - 若要画趋势线，请设置 action='trendline', t1, p1, t2, p2。\n"
        "严格约束: \n"
        "1. No Re-analysis: 禁止质疑 Analyzer 的信号，除非它违反了硬性风控。\n"
        "2. 不得更改止损: 严禁更改 Analyzer 传来的止损位 (SL)。\n"
        "3. JSON 完整性: 所有 UI 指令必须是严格的 JSON 格式，确保前端能够直接解析。\n"
        "4. 语言限制: 你的解释说明必须使用中文 (简体中文) 输出！严禁使用“好的”、“我知道了”等废话。\n"
        "执行结束后，请在末尾输出 'FINISHED'。"
    )
    executor_agent = create_react_agent(executor_llm, tools=[execute_ui_action], prompt=executor_prompt)
    
    def executor_node(state: AgentState):
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
                    if tc["name"] == "execute_ui_action":
                        args = tc.get('args', {})
                        # Ensure 'action' is present
                        if "type" in args and "action" not in args:
                            args["action"] = args["type"]
                        ui_actions.append(args)
                        
        msg.name = "executor"
        msg.additional_kwargs["ui_actions"] = ui_actions
        return {"messages": [msg]}
        
    # Supervisor
    class Route(BaseModel):
        next: Literal["analyzer", "executor", "FINISH"] = Field(
            description="Next step in the routing process. Choose 'analyzer' for market data, 'executor' to draw/act, or 'FINISH' if the task is complete."
        )

    system_prompt = (
        "角色: 你是 QuantLogicLab 自动化交易系统的最高统筹者 (Supervisor)。\n"
        "职责: 监控对话历史，并协调 'analyzer' 和 'executor' 两个子 Agent。\n"
        "操作流 (Operational Workflow) [基于历史中的最后一条消息判断]:\n"
        "1. 若最后一条消息来自用户且要求分析市场，路由至 'analyzer'。\n"
        "2. 若最后一条消息来自 'analyzer'：\n"
        "   - 若分析包含明确的交易信号或用户需要画图/执行，路由至 'executor'。\n"
        "   - 否则，路由至 'FINISH'。\n"
        "3. 若最后一条消息来自 'executor'，任务已闭环，路由至 'FINISH'。\n"
        "严格约束 (Strict Constraints):\n"
        "1. No Hallucination: 仅基于提供的 State 数据进行判断。严禁推测未提供的数据。\n"
        "2. 防止死循环: 严禁在单次对话中向同一个 Agent 路由两次！若该 Agent 已经回复过，立即路由至 'FINISH'。\n"
        "3. 遇到不确定或任务处于冷却期时，强制路由至 'FINISH'。\n"
        "4. 废话过滤: 严禁输出任何形式的开场白或“好的”、“我知道了”。\n"
    )

    def supervisor_node(state: AgentState):
        # Calculate recursion depth to prevent infinite loops
        recursion_count = len([m for m in state["messages"] if m.type == "ai"])
        if recursion_count > 10:
            print("Supervisor: Recursion limit reached, forcing FINISH.")
            return {"next": "FINISH"}

        messages = [
            {"role": "system", "content": system_prompt},
        ] + [
            {"role": m.type if m.type != "human" else "user", "content": f"[{m.name or 'user'}]: {m.content}"} 
            for m in state["messages"]
        ]
        
        prompt = messages[0]["content"] + "\n\nRespond ONLY with a JSON object containing the 'next' key (value can be 'analyzer', 'executor', or 'FINISH'). Do NOT output anything else."
        
        # Use bind(max_tokens=50) to force the LLM to reply instantly without generating long reasoning
        fast_llm = supervisor_llm.bind(max_tokens=50)
        # Try to enforce json_object if supported by provider
        try:
            fast_llm = fast_llm.bind(response_format={"type": "json_object"})
        except Exception:
            pass
        
        try:
            res = fast_llm.invoke([{"role": "system", "content": prompt}] + state["messages"])
            content = res.content.strip()
            
            # Print for debugging since test is failing
            print(f"Supervisor LLM raw output: {content}")
            print(f"Last message type: {state['messages'][-1].type}, content: {state['messages'][-1].content}")
            
            import re
            import json
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(0))
                    if "next" in data:
                        return {"next": data["next"]}
                except:
                    pass
            
            if "analyzer" in content.lower(): return {"next": "analyzer"}
            if "executor" in content.lower(): return {"next": "executor"}
            
            # If the user initiated the workflow (which usually implies they want an analysis or action)
            # and the LLM failed to give a valid JSON but also didn't explicitly say FINISH, 
            # we should default to routing it to analyzer to prevent immediate silent death.
            if "finish" not in content.upper():
                print("Supervisor fallback: LLM failed to route but didn't say FINISH. Defaulting to analyzer.")
                return {"next": "analyzer"}
                
            return {"next": "FINISH"}
        except Exception as e:
            print(f"Supervisor error: {e}")
            return {"next": "FINISH"}
        
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
