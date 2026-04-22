import asyncio
import json
import logging
from typing import Callable, Awaitable, Dict, List, Optional
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
    def __init__(self, pub_url: str = "tcp://127.0.0.1:5556"):
        self.pub_url = pub_url
        self.context = zmq.asyncio.Context()
        self._pub_socket: Optional[zmq.asyncio.Socket] = None
        self._sub_sockets: List[zmq.asyncio.Socket] = []
        self._running = False
        
    async def start(self):
        """Initialize the publisher socket."""
        if not self._pub_socket:
            self._pub_socket = self.context.socket(zmq.PUB)
            self._pub_socket.bind(self.pub_url)
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

    async def publish(self, topic: str, message: MarketMessage | SyncProgressMessage):
        """
        Publish a message to a specific topic.
        Topic format usually: "MARKET_DATA.{symbol}.{timeframe}" or "SYNC_PROGRESS.{symbol}"
        """
        if not self._pub_socket:
            logger.warning("Publisher socket not initialized. Call start() first.")
            return
            
        try:
            msg_data = message.model_dump_json()
            await self._pub_socket.send_multipart([topic.encode('utf-8'), msg_data.encode('utf-8')])
        except Exception as e:
            logger.error(f"Error publishing message: {e}")

    async def subscribe(self, topic: str, callback: Callable[[str, MarketMessage | SyncProgressMessage], Awaitable[None]]):
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
                    else:
                        msg_obj = MarketMessage.model_validate_json(msg_str)
                    await callback(topic_str, msg_obj)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error in subscriber loop for topic {topic}: {e}")
                    await asyncio.sleep(1) # Prevent tight loop on error
                    
        return asyncio.create_task(_listen())

# Singleton instance for application-wide use
message_bus = MessageBus()
