import asyncio
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from backend.services.agents.graph import build_multi_agent_graph
from backend.services.agents.communication import agent_comm
from langchain_core.messages import HumanMessage

router = APIRouter()

class AgentConfig(BaseModel):
    base_url: str = ""
    model: str = ""
    api_key: str = ""

class AIDecisionRequest(BaseModel):
    session_id: str
    message: str
    symbol: str = "XAUUSD"
    timeframe: str = "M15"
    configs: dict[str, AgentConfig] = {}  # "supervisor", "analyzer", "executor"

async def run_agent_workflow(session_id: str, initial_message: str, configs: dict, symbol: str, timeframe: str):
    """
    Background task to run the LangGraph workflow and broadcast status updates.
    """
    graph = build_multi_agent_graph(configs)
    
    # Inject context into the first message so tools know what symbol/tf to use
    context_msg = f"[System Context: User is viewing {symbol} on {timeframe} timeframe]\n\n{initial_message}"
    
    inputs = {
        "messages": [HumanMessage(content=context_msg)]
    }
    
    try:
        # Notify that supervisor is starting
        await agent_comm.broadcast_status(session_id, "supervisor", "thinking", "Analyzing task and planning route...")
        
        async for event in graph.astream(inputs, stream_mode="updates"):
            for node_name, state_update in event.items():
                if node_name == "supervisor":
                    next_route = state_update.get("next", "FINISH")
                    if next_route == "FINISH":
                        await agent_comm.broadcast_status(session_id, "supervisor", "finished", "Workflow completed.")
                    else:
                        await agent_comm.broadcast_status(session_id, "supervisor", "idle", f"Routing task to {next_route}...")
                        await agent_comm.broadcast_status(session_id, next_route, "thinking", "Starting work...")
                        
                elif node_name in ["analyzer", "executor"]:
                    # Get the last message output by the node
                    if "messages" in state_update and len(state_update["messages"]) > 0:
                        last_msg = state_update["messages"][-1]
                        msg_content = last_msg.content
                        
                        # Look for UI actions that were intercepted in the node
                        ui_actions = last_msg.additional_kwargs.get("ui_actions", [])
                        
                        # Also check if any message in the update has tool calls that match
                        if not ui_actions:
                            for m in state_update["messages"]:
                                if getattr(m, "tool_calls", None):
                                    for tc in m.tool_calls:
                                        if tc["name"] == "execute_ui_action":
                                            args = tc.get('args', {})
                                            if "type" in args and "action" not in args:
                                                args["action"] = args["type"]
                                            ui_actions.append(args)
                        
                        for action in ui_actions:
                            await agent_comm.broadcast_tool_execution(session_id, node_name, "execute_ui_action", action)
                            
                        await agent_comm.broadcast_status(session_id, node_name, "finished", msg_content)
                        await agent_comm.broadcast_status(session_id, "supervisor", "thinking", "Reviewing results...")

    except Exception as e:
        await agent_comm.broadcast_status(session_id, "supervisor", "error", f"Error occurred: {str(e)}")

@router.post("/trigger_decision")
async def trigger_ai_decision(request: AIDecisionRequest, background_tasks: BackgroundTasks):
    """
    Triggers the AI agent workflow asynchronously.
    Returns immediately so HTTP request doesn't timeout.
    """
    # Convert configs to dict
    configs_dict = {k: v.model_dump() for k, v in request.configs.items()}
    background_tasks.add_task(run_agent_workflow, request.session_id, request.message, configs_dict, request.symbol, request.timeframe)
    return {"status": "started", "session_id": request.session_id}

@router.post("/test_connection")
async def test_connection(request: AIDecisionRequest):
    """
    Tests the connection for each configured agent.
    Returns a dictionary of status for each agent.
    """
    configs_dict = {k: v.model_dump() for k, v in request.configs.items()}
    results = {}
    
    from backend.services.agents.graph import get_llm
    
    for role, config in configs_dict.items():
        if not config.get("api_key"):
            results[role] = {"status": "error", "message": "API Key is missing"}
            continue
            
        try:
            llm = get_llm(role, configs_dict)
            # A simple ping
            response = llm.invoke([{"role": "user", "content": "Ping. Reply with 'Pong' only."}])
            results[role] = {"status": "success", "message": "Connected"}
        except Exception as e:
            results[role] = {"status": "error", "message": str(e)}
            
    return results
