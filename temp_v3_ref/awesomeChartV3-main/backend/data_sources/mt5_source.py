import asyncio
import logging
import zmq
import zmq.asyncio
from typing import Dict, Any
from datetime import datetime

# Optional: MetaTrader5 for fallback polling
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

from backend.core.message_bus import message_bus, MarketMessage
from backend.core.event_store import event_store

logger = logging.getLogger(__name__)

class MT5Source:
    """
    Connects to MT5 Terminal via ZMQ (Primary) and MetaTrader5 Python API (Fallback).
    Pushes received data to the internal MessageBus.
    """
    def __init__(self, zmq_sub_url: str = "tcp://127.0.0.1:5555", use_zmq: bool = False):
        self.zmq_sub_url = zmq_sub_url
        self.use_zmq = use_zmq
        self.context = zmq.asyncio.Context()
        self._sub_socket = None
        self._running = False
        self._last_received_time = 0
        self._poll_interval = 1.0 # seconds before triggering fallback (1s for pure polling)
        
        # Now we only connect when explicitly requested via connect_broker
        self._broker_id = None

    def connect_broker(self, server: str, login: str, password: str = "", path: str = "") -> bool:
        """Dynamically connect to an MT5 broker."""
        if not MT5_AVAILABLE:
            logger.error("MT5 Python API is not installed or available.")
            return False
            
        kwargs = {}
        if path: kwargs['path'] = path
        if login: kwargs['login'] = int(login)
        if password: kwargs['password'] = password
        if server: kwargs['server'] = server
        
        # Shutdown existing connection if any
        mt5.shutdown()
        
        # mt5.initialize accepts **kwargs, but passing an empty server/login/password can sometimes cause issues.
        # If ONLY server is provided (without login/password), mt5.initialize() behaves weirdly or fails.
        # To just connect to the active terminal's current account, we should call mt5.initialize() without kwargs
        # if only 'server' is provided but no login credentials.
        if not login and not password and not path:
            # Connect to whatever is currently active in the terminal
            # If MT5 is not running, mt5.initialize() will attempt to start it automatically
            success = mt5.initialize()
            if not success:
                logger.error(f"Failed to connect MT5 (Default). Error: {mt5.last_error()}")
                # 尝试再次强制初始化
                logger.info("Attempting to force start MT5...")
                import time
                time.sleep(2)
                success = mt5.initialize()
                if not success:
                    return False
        else:
            success = mt5.initialize(**kwargs)
            if not success:
                logger.error(f"Failed to connect MT5: {kwargs}. Error: {mt5.last_error()}")
                logger.info("Attempting to force start MT5 with kwargs...")
                import time
                time.sleep(2)
                success = mt5.initialize(**kwargs)
                if not success:
                    return False
            
        # We also need to login if we provided credentials but no path, etc.
        if login and password and server:
            login_success = mt5.login(login=int(login), password=password, server=server)
            if not login_success:
                logger.error(f"Failed to login MT5: {login}@{server}. Error: {mt5.last_error()}")
                return False
                
        logger.info(f"Successfully connected to MT5 broker: {server} (Login: {login if login else 'Default'})")
        return True

    async def start(self):
        self._running = True
        self._last_received_time = asyncio.get_event_loop().time()
        
        if self.use_zmq:
            self._sub_socket = self.context.socket(zmq.SUB)
            self._sub_socket.connect(self.zmq_sub_url)
            self._sub_socket.setsockopt_string(zmq.SUBSCRIBE, "") # Subscribe to all topics from EA
            logger.info(f"MT5Source ZMQ Subscriber connected to {self.zmq_sub_url}")
            # Start listening loop
            asyncio.create_task(self._listen_loop())
        else:
            logger.info("MT5Source starting in PURE POLLING mode (ZMQ disabled)")
            
        # Start watchdog for fallback / pure polling
        asyncio.create_task(self._watchdog_loop())

    async def stop(self):
        self._running = False
        if self._sub_socket:
            self._sub_socket.close()
        self.context.term()
        if MT5_AVAILABLE:
            mt5.shutdown()
        logger.info("MT5Source stopped")

    async def _listen_loop(self):
        while self._running:
            try:
                # Wait for ZMQ message from EA
                msg = await asyncio.wait_for(self._sub_socket.recv_json(), timeout=1.0)
                self._last_received_time = asyncio.get_event_loop().time()
                
                # Assume msg from EA has format:
                # {"symbol": "EURUSD", "timeframe": "M1", "time": 1600000000, "open": 1.1, ...}
                msg['source'] = 'zmq'
                
                # Record raw event
                event_store.record_event(f"MT5_RAW.{msg.get('symbol')}", msg)
                
                # Convert to internal MarketMessage
                market_msg = MarketMessage(**msg)
                
                # Publish to internal MessageBus
                topic = f"MARKET_DATA.{market_msg.symbol}.{market_msg.timeframe}"
                await message_bus.publish(topic, market_msg)
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error in MT5Source listen loop: {e}")
                await asyncio.sleep(1)

    async def _watchdog_loop(self):
        """Monitors ZMQ activity and triggers MT5 API polling if data stops."""
        while self._running:
            await asyncio.sleep(self._poll_interval)
            now = asyncio.get_event_loop().time()
            if not self.use_zmq or (now - self._last_received_time > self._poll_interval):
                # ZMQ is quiet or disabled, trigger poll
                await self._trigger_poll()
                # Reset timer so we don't poll too frantically
                self._last_received_time = now

    async def _trigger_poll(self):
        """Fallback mechanism using MT5 Python API to fetch latest data."""
        if not MT5_AVAILABLE:
            return
            
        # Dynamically fetch active symbols from the active broker's metastore
        from backend.api.dependencies import get_current_broker_deps
        deps = get_current_broker_deps()
        if not deps:
            return
            
        meta_store = deps['meta_store']
        active_symbols = meta_store.get_active_symbols()
        
        for symbol, timeframes in active_symbols.items():
            for tf in timeframes:
                # Convert TF string to MT5 timeframe constant
                mt5_tf = self._get_mt5_timeframe(tf)
                if mt5_tf is None: continue
                
                # Fetch last 2 bars just to be safe
                rates = mt5.copy_rates_from_pos(symbol, mt5_tf, 0, 2)
                if rates is not None and len(rates) > 0:
                    for rate in rates:
                        msg = {
                            "symbol": symbol,
                            "timeframe": tf,
                            "time": int(rate['time']),
                            "open": float(rate['open']),
                            "high": float(rate['high']),
                            "low": float(rate['low']),
                            "close": float(rate['close']),
                            "tick_volume": int(rate['tick_volume']),
                            "delta_volume": 0, # MT5 doesn't provide delta by default
                            "source": "poll"
                        }
                        
                        event_store.record_event(f"MT5_RAW_POLL.{symbol}", msg)
                        market_msg = MarketMessage(**msg)
                        topic = f"MARKET_DATA.{symbol}.{tf}"
                        await message_bus.publish(topic, market_msg)

    def _get_mt5_timeframe(self, tf_str: str):
        if not MT5_AVAILABLE: return None
        mapping = {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
            "W1": mt5.TIMEFRAME_W1,
            "MN1": mt5.TIMEFRAME_MN1,
        }
        return mapping.get(tf_str)

mt5_source = MT5Source(use_zmq=False)
