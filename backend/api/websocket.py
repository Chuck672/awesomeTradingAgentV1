from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
import logging
import asyncio
import time
import weakref
from collections import deque
from typing import Dict, Set, Any, Optional

from backend.core.message_bus import message_bus, MarketMessage, SyncProgressMessage

logger = logging.getLogger(__name__)

router = APIRouter()

class ConnectionManager:
    def __init__(self):
        # Maps "symbol:timeframe" to a set of active WebSockets
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.global_connections: Set[WebSocket] = set()
        self._market_log_ts: Dict[str, int] = {}
        self._market_msg_count: Dict[str, int] = {}
        self._send_locks: "weakref.WeakKeyDictionary[WebSocket, asyncio.Lock]" = weakref.WeakKeyDictionary()
        self._global_queue: "deque[dict]" = deque()
        self._global_flush_task: Optional[asyncio.Task] = None
        self._market_latest: Dict[str, dict] = {}
        self._market_flush_tasks: Dict[str, asyncio.Task] = {}

    def _get_lock(self, websocket: WebSocket) -> asyncio.Lock:
        lock = self._send_locks.get(websocket)
        if lock is None:
            lock = asyncio.Lock()
            self._send_locks[websocket] = lock
        return lock

    def _is_connected(self, websocket: WebSocket) -> bool:
        try:
            return (
                websocket.client_state == WebSocketState.CONNECTED
                and websocket.application_state == WebSocketState.CONNECTED
            )
        except Exception:
            return False

    def _is_expected_disconnect_error(self, e: Exception) -> bool:
        if isinstance(e, WebSocketDisconnect):
            return True
        msg = str(e)
        return (
            "Unexpected ASGI message 'websocket.send'" in msg
            or "Cannot call \"send\" once a close message has been sent" in msg
            or "after sending 'websocket.close'" in msg
        )

    async def _safe_send_json(self, websocket: WebSocket, message: dict) -> bool:
        if not self._is_connected(websocket):
            return False
        lock = self._get_lock(websocket)
        async with lock:
            if not self._is_connected(websocket):
                return False
            try:
                await asyncio.wait_for(websocket.send_json(message), timeout=2.5)
                return True
            except Exception as e:
                if self._is_expected_disconnect_error(e):
                    logger.debug("ws_send expected_disconnect err=%s", repr(e))
                else:
                    logger.warning("ws_send failed err=%s", repr(e), exc_info=True)
                return False

    async def connect(self, websocket: WebSocket, symbol: str, timeframe: str):
        await websocket.accept()
        if symbol == "AGENT" and timeframe == "SYSTEM":
            self.global_connections.add(websocket)
            logger.info(f"Client connected to GLOBAL. Total clients: {len(self.global_connections)}")
            return
        topic = f"{symbol}:{timeframe}"
        if topic not in self.active_connections:
            self.active_connections[topic] = set()
        self.active_connections[topic].add(websocket)
        logger.info(f"Client connected to {topic}. Total clients: {len(self.active_connections[topic])}")

    def disconnect(self, websocket: WebSocket, symbol: str, timeframe: str):
        if symbol == "AGENT" and timeframe == "SYSTEM":
            if websocket in self.global_connections:
                self.global_connections.remove(websocket)
                logger.info(f"Client disconnected from GLOBAL. Remaining: {len(self.global_connections)}")
            return
        topic = f"{symbol}:{timeframe}"
        if topic in self.active_connections and websocket in self.active_connections[topic]:
            self.active_connections[topic].remove(websocket)
            logger.info(f"Client disconnected from {topic}. Remaining: {len(self.active_connections[topic])}")
            if not self.active_connections[topic]:
                del self.active_connections[topic]

    async def broadcast_global(self, message: dict):
        if not self.global_connections:
            return
        websockets = list(self.global_connections)
        for connection in websockets:
            try:
                ok = await self._safe_send_json(connection, message)
                if not ok:
                    raise RuntimeError("send_failed")
            except Exception as e:
                if self._is_expected_disconnect_error(e) or str(e) == "send_failed":
                    logger.debug(f"Error broadcasting to GLOBAL: {repr(e)}")
                else:
                    logger.warning(f"Error broadcasting to GLOBAL: {repr(e)}")
                self.global_connections.discard(connection)

    async def broadcast(self, topic: str, message: dict):
        if topic in self.active_connections:
            # Create a list of sockets to iterate over safely
            websockets = list(self.active_connections[topic])
            for connection in websockets:
                try:
                    ok = await self._safe_send_json(connection, message)
                    if not ok:
                        raise RuntimeError("send_failed")
                except Exception as e:
                    if self._is_expected_disconnect_error(e) or str(e) == "send_failed":
                        logger.debug(f"Error broadcasting to {topic}: {repr(e)}")
                    else:
                        logger.warning(f"Error broadcasting to {topic}: {repr(e)}")
                    if topic in self.active_connections:
                        self.active_connections[topic].discard(connection)
                        if not self.active_connections[topic]:
                            del self.active_connections[topic]

    def enqueue_global(self, message: dict) -> None:
        self._global_queue.append(message)
        if self._global_flush_task and not self._global_flush_task.done():
            return
        self._global_flush_task = asyncio.create_task(self._flush_global())

    async def _flush_global(self) -> None:
        while self._global_queue:
            msg = self._global_queue.popleft()
            await self.broadcast_global(msg)
            await asyncio.sleep(0)

    def enqueue_market(self, topic: str, message: dict) -> None:
        self._market_latest[topic] = message
        t = self._market_flush_tasks.get(topic)
        if t and not t.done():
            return
        self._market_flush_tasks[topic] = asyncio.create_task(self._flush_market(topic))

    async def _flush_market(self, topic: str) -> None:
        while True:
            msg = self._market_latest.pop(topic, None)
            if msg is None:
                return
            await self.broadcast(topic, msg)
            await asyncio.sleep(0)

manager = ConnectionManager()

# Background task reference to hold the message bus subscription
_ws_tasks = []

async def _ws_message_handler(topic: str, msg: Any):
    """
    Callback for message_bus to handle incoming ZeroMQ messages
    and route them to connected WebSocket clients.
    """
    if topic.startswith("AGENT_STATUS"):
        frontend_msg = msg if isinstance(msg, dict) else msg.model_dump()
        try:
            asyncio.get_running_loop()
            manager.enqueue_global(frontend_msg)
        except RuntimeError:
            asyncio.run(manager.broadcast_global(frontend_msg))
        return

    if topic.startswith("SYNC_PROGRESS"):
        frontend_msg = msg.model_dump()
        try:
            asyncio.get_running_loop()
            manager.enqueue_global(frontend_msg)
        except RuntimeError:
            asyncio.run(manager.broadcast_global(frontend_msg))
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
    try:
        now = int(time.time())
        manager._market_msg_count[ws_topic] = int(manager._market_msg_count.get(ws_topic, 0)) + 1
        last_ts = int(manager._market_log_ts.get(ws_topic, 0))
        if now - last_ts >= 30:
            manager._market_log_ts[ws_topic] = now
            c = int(manager._market_msg_count.get(ws_topic, 0))
            manager._market_msg_count[ws_topic] = 0
            logger.info("market_ws_flow topic=%s msgs_30s=%s last_close=%s", ws_topic, c, msg.close)
    except Exception:
        logger.debug("market_ws_flow_log_failed topic=%s", ws_topic, exc_info=True)
    try:
        asyncio.get_running_loop()
        manager.enqueue_market(ws_topic, frontend_msg)
    except RuntimeError:
        asyncio.run(manager.broadcast(ws_topic, frontend_msg))

async def start_ws_subscription():
    """Start listening to the message bus for WebSocket distribution"""
    global _ws_tasks
    _ws_tasks = [
        await message_bus.subscribe("MARKET_DATA", _ws_message_handler),
        await message_bus.subscribe("SYNC_PROGRESS", _ws_message_handler),
        await message_bus.subscribe("AGENT_STATUS", _ws_message_handler),
    ]

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
