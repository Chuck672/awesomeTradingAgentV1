import asyncio
import logging
from typing import AsyncGenerator, Optional
from backend.core.message_bus import MarketMessage
from backend.services.historical import historical_service

logger = logging.getLogger(__name__)

class ReplayService:
    """
    Simulates live market data by streaming historical data at a controlled speed.
    Useful for frontend Bar Replay features.
    """
    def __init__(self):
        self.active_sessions = {}

    async def stream_replay(
        self, 
        session_id: str,
        symbol: str, 
        timeframe: str, 
        start_time: int, 
        speed_ms: int = 1000
    ) -> AsyncGenerator[MarketMessage, None]:
        """
        Fetches historical data starting from start_time and yields it bar by bar.
        speed_ms is the delay between emitting each bar.
        """
        logger.info(f"Starting replay session {session_id} for {symbol} {timeframe} at {start_time}")
        self.active_sessions[session_id] = True
        
        # In a real scenario, we might want to query data in chunks to avoid loading
        # massive amounts of history into memory all at once.
        # For simplicity, let's fetch a chunk and yield.
        chunk_size = 1000
        current_time = start_time
        
        try:
            while self.active_sessions.get(session_id, False):
                # We need data *after* current_time (ascending order)
                # Our historical_service.get_history usually returns latest `limit` bars before a `before_time`
                # Wait, get_history gets bars BEFORE a certain time, sorted DESC. 
                # For replay, we need bars AFTER a certain time, sorted ASC.
                # We might need a new method in historical_service for this, or use raw DuckDB query.
                
                # Let's write a direct query for now or assume we can add it to historical_service
                from backend.api.dependencies import get_current_broker_deps
                deps = get_current_broker_deps()
                if not deps:
                    break
                sqlite_manager = deps['sqlite_manager']
                
                query = f"""
                    SELECT time, open, high, low, close, tick_volume, delta_volume FROM ohlcv 
                    WHERE symbol = '{symbol}' AND timeframe = '{timeframe}' AND time >= {current_time}
                    ORDER BY time ASC
                    LIMIT {chunk_size}
                """
                
                import sqlite3
                with sqlite3.connect(sqlite_manager.db_path) as conn:
                    cursor = conn.cursor()
                    rows = cursor.execute(query).fetchall()
                if not rows:
                    logger.info(f"Replay session {session_id} reached end of data.")
                    break
                    
                for row in rows:
                    if not self.active_sessions.get(session_id, False):
                        break
                        
                    msg = MarketMessage(
                        symbol=symbol,
                        timeframe=timeframe,
                        time=row[0],
                        open=row[1],
                        high=row[2],
                        low=row[3],
                        close=row[4],
                        tick_volume=row[5] or 0,
                        delta_volume=row[6] or 0,
                        source="replay"
                    )
                    
                    yield msg
                    
                    # Update current_time for next chunk query (time of last yielded bar + 1)
                    current_time = row[0] + 1
                    
                    # Wait according to speed
                    await asyncio.sleep(speed_ms / 1000.0)
                    
        except asyncio.CancelledError:
            logger.info(f"Replay session {session_id} cancelled.")
        except Exception as e:
            logger.error(f"Error in replay session {session_id}: {e}")
        finally:
            self.stop_replay(session_id)
            
    def stop_replay(self, session_id: str):
        if session_id in self.active_sessions:
            self.active_sessions[session_id] = False
            logger.info(f"Stopped replay session {session_id}")

replay_service = ReplayService()
