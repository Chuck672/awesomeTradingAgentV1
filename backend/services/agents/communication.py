import asyncio
import json
from typing import Optional, Dict, Any

from langchain_core.messages import BaseMessage
from pydantic import BaseModel

from backend.core.message_bus import message_bus

class AgentStatusMessage(BaseModel):
    """
    Message broadcasted to frontend when Agent state changes.
    """
    type: str = "agent_status"
    session_id: str
    current_agent: str  # "supervisor", "analyzer", "executor", "idle"
    status: str         # "thinking", "acting", "idle", "finished", "error"
    latest_message: str = ""

class AgentCommunicationLayer:
    """
    Handles intercepting LangGraph events and broadcasting them via message_bus.
    """
    def __init__(self):
        self.active_sessions: Dict[str, str] = {}

    async def broadcast_status(
        self, 
        session_id: str, 
        current_agent: str, 
        status: str, 
        latest_message: str = ""
    ):
        """
        Broadcasts the current agent status to the frontend via message_bus.
        """
        msg = AgentStatusMessage(
            session_id=session_id,
            current_agent=current_agent,
            status=status,
            latest_message=latest_message
        )
        # We publish to a specific topic that the websocket handler will listen to
        await message_bus.publish("AGENT_STATUS", msg)

    async def broadcast_tool_execution(self, session_id: str, agent: str, tool: str, payload: dict):
        """
        Broadcasts a tool execution event to the frontend so it can render UI directly without regex parsing.
        """
        msg = {
            "type": "tool_execution",
            "session_id": session_id,
            "agent": agent,
            "tool": tool,
            "payload": payload
        }
        await message_bus.publish("AGENT_STATUS", msg)

agent_comm = AgentCommunicationLayer()
