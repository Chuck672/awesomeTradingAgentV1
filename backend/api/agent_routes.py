import asyncio
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from backend.services.agents.graph import build_multi_agent_graph
from backend.services.agents.communication import agent_comm
from langchain_core.messages import HumanMessage

router = APIRouter()

# Global dictionary to track active agent workflow tasks
active_tasks: dict[str, asyncio.Task] = {}

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
    image_data: str | None = None  # Base64 encoded image data for multimodal input

class CancelRequest(BaseModel):
    session_id: str

async def run_agent_workflow(session_id: str, initial_message: str, configs: dict, symbol: str, timeframe: str, image_data: str | None = None, alert_id: int | None = None, telegram_config: dict | None = None):
    """
    Background task to run the LangGraph workflow and broadcast status updates.
    """
    graph = build_multi_agent_graph(configs)
    
    # Inject context into the first message so tools know what symbol/tf to use
    context_msg = f"[System Context: User is viewing {symbol} on {timeframe} timeframe]\n\n{initial_message}"
    
    if image_data:
        # Multimodal message
        # image_data might already have the data:image/png;base64, prefix. If not, we should handle it.
        # Assuming frontend sends it with the prefix or without it. Let's just ensure it's properly formatted for LangChain.
        # LangChain expects the base64 string or image_url dictionary.
        
        # Ensure it has the data URI prefix if it's base64
        image_url = image_data if image_data.startswith("data:image") else f"data:image/png;base64,{image_data}"
        
        content = [
            {"type": "text", "text": context_msg},
            {"type": "image_url", "image_url": {"url": image_url}}
        ]
        inputs = {
            "messages": [HumanMessage(content=content)]
        }
    else:
        inputs = {
            "messages": [HumanMessage(content=context_msg)]
        }
    
    report_lines = []
    report_lines.append(f"🚨 **Trigger Event**: {initial_message}")
    
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
                        
                        if msg_content:
                            report_lines.append(f"**{node_name.capitalize()}**: {msg_content}")
                            
                        # Look for UI actions that were intercepted in the node
                        ui_actions = last_msg.additional_kwargs.get("ui_actions", [])
                        
                        # Also check if any message in the update has tool calls that match
                        if not ui_actions:
                            for m in state_update["messages"]:
                                if getattr(m, "tool_calls", None):
                                    for tc in m.tool_calls:
                                        if tc["name"].startswith(("chart_", "draw_", "indicator_", "execute_ui_action")):
                                            args = tc.get('args', {})
                                            if "type" in args and "action" not in args:
                                                args["action"] = args["type"]
                                            if tc["name"] != "execute_ui_action":
                                                args["action"] = tc["name"]
                                            ui_actions.append(args)
                        
                        for action in ui_actions:
                            report_lines.append(f"🛠️ **Action**: `{action.get('action')}`")
                            await agent_comm.broadcast_tool_execution(session_id, node_name, action.get("action", "execute_ui_action"), action)
                            
                        await agent_comm.broadcast_status(session_id, node_name, "finished", msg_content)
                        await agent_comm.broadcast_status(session_id, "supervisor", "thinking", "Reviewing results...")

        # After workflow finishes, if it's a background alert task, save and notify
        if alert_id is not None:
            final_report = "\n\n".join(report_lines)
            try:
                from backend.services.alerts_store import save_ai_report
                save_ai_report(alert_id, session_id, final_report)
            except Exception as e:
                print(f"Failed to save AI report: {e}")
                
            if telegram_config:
                token = telegram_config.get("token")
                chat_id = telegram_config.get("chat_id")
                if token and chat_id:
                    from backend.services.telegram import send_telegram_message
                    try:
                        # Send telegram message (this might be sync, so use asyncio.to_thread if needed, but it uses requests)
                        import asyncio
                        await asyncio.to_thread(send_telegram_message, bot_token=token, chat_id=chat_id, text=final_report)
                    except Exception as e:
                        print(f"Failed to send telegram message: {e}")

    except asyncio.CancelledError:
        # Handle task cancellation gracefully
        print(f"Workflow for session {session_id} was cancelled.")
        await agent_comm.broadcast_status(session_id, "supervisor", "idle", "Workflow was manually stopped by user.")
        await agent_comm.broadcast_status(session_id, "analyzer", "idle", "")
        await agent_comm.broadcast_status(session_id, "executor", "idle", "")
        raise  # Re-raise to ensure the task is properly marked as cancelled
    except Exception as e:
        await agent_comm.broadcast_status(session_id, "supervisor", "error", f"Error occurred: {str(e)}")

@router.post("/trigger_decision")
async def trigger_ai_decision(request: AIDecisionRequest):
    """
    Triggers the AI agent workflow asynchronously.
    Returns immediately so HTTP request doesn't timeout.
    """
    # Cancel existing task for this session if any
    if request.session_id in active_tasks:
        active_tasks[request.session_id].cancel()
        
    # Convert configs to dict
    configs_dict = {k: v.model_dump() for k, v in request.configs.items()}
    
    # Create an asyncio Task instead of using BackgroundTasks to allow cancellation
    task = asyncio.create_task(
        run_agent_workflow(request.session_id, request.message, configs_dict, request.symbol, request.timeframe, request.image_data)
    )
    
    # Store the task and add a callback to remove it when done
    active_tasks[request.session_id] = task
    task.add_done_callback(lambda t: active_tasks.pop(request.session_id, None))
    
    return {"status": "started", "session_id": request.session_id}

@router.post("/cancel_decision")
async def cancel_ai_decision(request: CancelRequest):
    """
    Cancels a currently running AI workflow for a given session.
    """
    task = active_tasks.get(request.session_id)
    if not task:
        return {"status": "not_found", "message": "No active task found for this session."}
        
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
        
    return {"status": "cancelled", "session_id": request.session_id}

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
