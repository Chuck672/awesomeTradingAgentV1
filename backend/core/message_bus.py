import asyncio
import json
import logging
import os
from typing import Callable, Awaitable, Dict, List, Optional, Any
import zmq
import zmq.asyncio
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class MarketMessage(BaseModel):
    """
    Standardized market data message format for internal routing.
    """
    symbol: str
    timeframe: str
    time: int
    open: float
    high: float
    low: float
    close: float
    tick_volume: int = 0
    delta_volume: int = 0
    source: str = Field(default="zmq", description="Source of the data: 'zmq' or 'poll'")

class SyncProgressMessage(BaseModel):
    """
    Standardized message for broadcasting data sync progress.
    """
    type: str = "sync_progress"
    symbol: str
    timeframe: str
    progress: int  # 0 to 100
    status: str    # "syncing", "completed", "error"
    message: str = ""

class MessageBus:
    """
    Central async message bus using ZeroMQ PUB/SUB pattern.
    Allows decoupling of data ingestion, storage, and WebSocket distribution.
    """
    def __init__(self, pub_url: str = "tcp://127.0.0.1:5557"):
        self.pub_url = os.environ.get("AWESOMECHART_MESSAGE_BUS_URL", "").strip() or pub_url
        self.context = zmq.asyncio.Context()
        self._pub_socket: Optional[zmq.asyncio.Socket] = None
        self._sub_sockets: List[zmq.asyncio.Socket] = []
        self._running = False
        
    async def start(self):
        """Initialize the publisher socket."""
        if not self._pub_socket:
            self._pub_socket = self.context.socket(zmq.PUB)
            last_err: Exception | None = None
            bound = False
            base = self.pub_url
            host = None
            port = None
            if base.startswith("tcp://") and base.count(":") >= 2:
                try:
                    host = base.rsplit(":", 1)[0]
                    port = int(base.rsplit(":", 1)[1])
                except Exception:
                    host = None
                    port = None

            if host is not None and port is not None:
                for p in range(port, port + 50):
                    try:
                        url = f"{host}:{p}"
                        self._pub_socket.bind(url)
                        self.pub_url = url
                        bound = True
                        break
                    except Exception as e:
                        last_err = e
                        continue
            else:
                try:
                    self._pub_socket.bind(self.pub_url)
                    bound = True
                except Exception as e:
                    last_err = e

            if not bound:
                raise last_err or RuntimeError("message_bus_bind_failed")
            logger.info(f"MessageBus Publisher started on {self.pub_url}")
            self._running = True

    async def stop(self):
        """Stop all sockets and context."""
        self._running = False
        if self._pub_socket:
            self._pub_socket.close()
        for sub_socket in self._sub_sockets:
            sub_socket.close()
        self.context.term()
        logger.info("MessageBus stopped")

    async def publish(self, topic: str, message: Any):
        """
        Publish a message to a specific topic.
        Topic format usually: "MARKET_DATA.{symbol}.{timeframe}" or "SYNC_PROGRESS.{symbol}"
        """
        if not self._pub_socket:
            logger.warning("publish_dropped publisher_not_initialized topic=%s", topic)
            return
            
        try:
            if hasattr(message, 'model_dump_json'):
                msg_data = message.model_dump_json()
            else:
                # Fallback for dicts
                msg_data = json.dumps(message)
            await self._pub_socket.send_multipart([topic.encode('utf-8'), msg_data.encode('utf-8')])
        except Exception as e:
            logger.exception("publish_failed topic=%s err=%s", topic, str(e))

    async def subscribe(self, topic: str, callback: Callable[[str, Any], Awaitable[None]]):
        """
        Subscribe to a specific topic and trigger the callback when a message is received.
        Returns the asyncio task running the subscriber loop.
        """
        sub_socket = self.context.socket(zmq.SUB)
        # connect to the internal PUB socket instead of external
        # Wait, if we use SUB, it should connect to the PUB address
        # In a real distributed system, we might need a broker (XPUB/XSUB)
        # But for this local system, connecting SUB directly to PUB is fine
        sub_socket.connect(self.pub_url)
        sub_socket.setsockopt_string(zmq.SUBSCRIBE, topic)
        self._sub_sockets.append(sub_socket)
        
        logger.info(f"Subscribed to topic: {topic}")

        async def _listen():
            while self._running:
                try:
                    # Non-blocking wait for messages
                    topic_bytes, msg_bytes = await sub_socket.recv_multipart()
                    topic_str = topic_bytes.decode('utf-8')
                    msg_str = msg_bytes.decode('utf-8')
                    
                    # Trigger the async callback
                    if topic_str.startswith("SYNC_PROGRESS"):
                        msg_obj = SyncProgressMessage.model_validate_json(msg_str)
                    elif topic_str.startswith("AGENT_STATUS"):
                        msg_obj = json.loads(msg_str)
                    else:
                        msg_obj = MarketMessage.model_validate_json(msg_str)
                    await callback(topic_str, msg_obj)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.exception("subscriber_loop_failed topic=%s err=%s", topic, str(e))
                    await asyncio.sleep(1) # Prevent tight loop on error
                    
        return asyncio.create_task(_listen())

# Singleton instance for application-wide use
message_bus = MessageBus()
