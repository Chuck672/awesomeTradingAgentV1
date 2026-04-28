import asyncio
import logging
from fastapi import APIRouter
from pydantic import BaseModel

from backend.services.ai.llm_factory import get_llm
from backend.services.workflows.tri_agent_workflow import TriAgentWorkflow

router = APIRouter()
logger = logging.getLogger(__name__)

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
        TriAgentWorkflow.run(
            session_id=request.session_id,
            initial_message=request.message,
            configs=configs_dict,
            symbol=request.symbol,
            timeframe=request.timeframe,
            image_data=request.image_data,
        )
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

    for role, config in configs_dict.items():
        if not config.get("api_key"):
            results[role] = {"status": "error", "message": "API Key is missing"}
            continue
            
        try:
            llm = get_llm(role, configs_dict)
            # A simple ping
            response = await asyncio.to_thread(llm.invoke, [{"role": "user", "content": "Ping. Reply with 'Pong' only."}])
            results[role] = {"status": "success", "message": "Connected"}
        except Exception as e:
            results[role] = {"status": "error", "message": str(e)}
            
    return results
