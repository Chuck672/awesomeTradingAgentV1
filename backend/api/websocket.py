from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import logging
from typing import Dict, Set, Any

from backend.core.message_bus import message_bus, MarketMessage, SyncProgressMessage

logger = logging.getLogger(__name__)

router = APIRouter()

class ConnectionManager:
    def __init__(self):
        # Maps "symbol:timeframe" to a set of active WebSockets
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, symbol: str, timeframe: str):
        await websocket.accept()
        topic = f"{symbol}:{timeframe}"
        if topic not in self.active_connections:
            self.active_connections[topic] = set()
        self.active_connections[topic].add(websocket)
        logger.info(f"Client connected to {topic}. Total clients: {len(self.active_connections[topic])}")

    def disconnect(self, websocket: WebSocket, symbol: str, timeframe: str):
        topic = f"{symbol}:{timeframe}"
        if topic in self.active_connections and websocket in self.active_connections[topic]:
            self.active_connections[topic].remove(websocket)
            logger.info(f"Client disconnected from {topic}. Remaining: {len(self.active_connections[topic])}")
            if not self.active_connections[topic]:
                del self.active_connections[topic]

    async def broadcast(self, topic: str, message: dict):
        if topic in self.active_connections:
            # Create a list of sockets to iterate over safely
            websockets = list(self.active_connections[topic])
            for connection in websockets:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"Error broadcasting to {topic}: {e}")
                    # Usually we let WebSocketDisconnect handle cleanup, but just in case
                    pass

manager = ConnectionManager()

# Background task reference to hold the message bus subscription
_ws_task = None

async def _ws_message_handler(topic: str, msg: Any):
    """
    Callback for message_bus to handle incoming ZeroMQ messages
    and route them to connected WebSocket clients.
    """
    if topic.startswith("AGENT_STATUS"):
        # Broadcast agent status to all connected clients
        target_ws_topics = list(manager.active_connections.keys())
        frontend_msg = msg if isinstance(msg, dict) else msg.model_dump()
        
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            for ws_topic in target_ws_topics:
                if loop.is_running():
                    asyncio.create_task(manager.broadcast(ws_topic, frontend_msg))
                else:
                    asyncio.run(manager.broadcast(ws_topic, frontend_msg))
        except RuntimeError:
            for ws_topic in target_ws_topics:
                asyncio.run(manager.broadcast(ws_topic, frontend_msg))
        return

    if topic.startswith("SYNC_PROGRESS"):
        # Broadcast to ALL active clients regardless of what symbol they are viewing,
        # because the frontend uses any active connection to listen to global progress.
        target_ws_topics = list(manager.active_connections.keys())
        frontend_msg = msg.model_dump()
        
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            for ws_topic in target_ws_topics:
                if loop.is_running():
                    asyncio.create_task(manager.broadcast(ws_topic, frontend_msg))
                else:
                    asyncio.run(manager.broadcast(ws_topic, frontend_msg))
        except RuntimeError:
            for ws_topic in target_ws_topics:
                asyncio.run(manager.broadcast(ws_topic, frontend_msg))
        return

    # Normal Market Data handling
    # The message bus topic is typically "MARKET_DATA.{symbol}.{timeframe}"
    # We want to broadcast to "{symbol}:{timeframe}"
    # So we extract symbol and timeframe from the message directly
    ws_topic = f"{msg.symbol}:{msg.timeframe}"
    
    # Format message for frontend Lightweight Charts
    frontend_msg = {
        "type": "update",
        "data": {
            "time": msg.time,
            "open": msg.open,
            "high": msg.high,
            "low": msg.low,
            "close": msg.close,
            "volume": msg.tick_volume,
            "delta_volume": msg.delta_volume
        }
    }
    
    # We must ensure that the event loop running the WebSocket server handles the broadcast
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            asyncio.create_task(manager.broadcast(ws_topic, frontend_msg))
        else:
            asyncio.run(manager.broadcast(ws_topic, frontend_msg))
    except RuntimeError:
        asyncio.run(manager.broadcast(ws_topic, frontend_msg))

async def start_ws_subscription():
    """Start listening to the message bus for WebSocket distribution"""
    global _ws_task
    # Subscribe to ALL market data (topic="")
    _ws_task = await message_bus.subscribe("", _ws_message_handler)

@router.websocket("/ws/{symbol}/{timeframe}")
async def websocket_endpoint(websocket: WebSocket, symbol: str, timeframe: str):
    await manager.connect(websocket, symbol, timeframe)
    try:
        while True:
            # We don't expect much from the client right now, 
            # but we need to keep the connection open and listen for disconnects
            data = await websocket.receive_text()
            # Handle potential client messages (e.g. ping/pong or configuration changes)
    except WebSocketDisconnect:
        manager.disconnect(websocket, symbol, timeframe)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket, symbol, timeframe)
