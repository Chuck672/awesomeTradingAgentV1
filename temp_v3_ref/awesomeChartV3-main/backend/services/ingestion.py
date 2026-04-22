import asyncio
import logging
from typing import List, Dict, Any
from datetime import datetime, timezone
import calendar

from backend.core.message_bus import message_bus, MarketMessage
from backend.api.dependencies import get_current_broker_deps
from backend.data_sources.mt5_source import MT5_AVAILABLE

if MT5_AVAILABLE:
    import MetaTrader5 as mt5

logger = logging.getLogger(__name__)

class IngestionService:
    """
    Handles data reconciliation, catch-up (断点续传), and archiving.
    Subscribes to MarketMessage and persists to DuckDB.
    """
    def __init__(self):
        self._buffer: List[Dict[str, Any]] = []
        self._batch_size = 50
        self._flush_task = None
        self._is_running = False
        self.active_progress: Dict[tuple, Dict[str, Any]] = {}

    async def _publish_progress(self, symbol: str, timeframe: str, progress: int, status: str, message: str):
        self.active_progress[(symbol, timeframe)] = {
            "symbol": symbol,
            "timeframe": timeframe,
            "progress": progress,
            "status": status,
            "message": message
        }
        from backend.core.message_bus import message_bus, SyncProgressMessage
        await message_bus.publish(
            f"SYNC_PROGRESS.{symbol}",
            SyncProgressMessage(
                symbol=symbol, timeframe=timeframe, progress=progress, status=status, 
                message=message
            )
        )

    async def start(self):
        self._is_running = True
        
        # Bug Fix: 在订阅实时行情之前，先读取所有周期断线前的最后同步时间
        # 防止重启后瞬间涌入的新 K 线把 last_sync 刷新为当前时间，导致跳过 Catch-up 断点续传
        self._initial_sync_states = {}
        deps = get_current_broker_deps()
        if deps:
            meta_store = deps['meta_store']
            active_symbols = meta_store.get_active_symbols()
            for sym, tfs in active_symbols.items():
                for tf in tfs:
                    self._initial_sync_states[(sym, tf)] = meta_store.get_sync_state(sym, tf)
                    
        # Subscribe to all MARKET_DATA topics
        await message_bus.subscribe("MARKET_DATA", self._handle_market_message)
        
        # Start periodic background flush task
        self._flush_task = asyncio.create_task(self._periodic_flush())
        
        # Start initial reconciliation for active broker
        asyncio.create_task(self._reconcile_all_active_symbols())
        
        logger.info("IngestionService started")

    async def stop(self):
        self._is_running = False
        if self._flush_task:
            self._flush_task.cancel()
        await self._flush_buffer()
        logger.info("IngestionService stopped")

    async def _handle_market_message(self, topic: str, msg: MarketMessage):
        """Buffer incoming real-time messages."""
        self._buffer.append(msg.model_dump())
        
        if len(self._buffer) >= self._batch_size:
            await self._flush_buffer()

    async def _periodic_flush(self):
        """Periodically flush buffer even if batch size isn't met."""
        while self._is_running:
            await asyncio.sleep(2.0)
            if self._buffer:
                await self._flush_buffer()

    async def _flush_buffer(self):
        if not self._buffer:
            return
            
        bars_to_insert = self._buffer.copy()
        self._buffer.clear()
        
        deps = get_current_broker_deps()
        if not deps:
            logger.warning("No active broker to flush data to.")
            return
            
        sqlite_manager = deps['sqlite_manager']
        
        # Insert into SQLite
        await sqlite_manager.upsert_bars(bars_to_insert)
        
        # Update last sync time in config store
        latest_times = {}
        for b in bars_to_insert:
            key = (b['symbol'], b['timeframe'])
            if key not in latest_times or b['time'] > latest_times[key]:
                latest_times[key] = b['time']
                
        for (symbol, tf), time in latest_times.items():
            sqlite_manager.update_sync_state(symbol, tf, time)
            
        # Check if there are active background syncs that we should publish progress for
        # Since this is called frequently, we can optionally broadcast that we are "live syncing"
        # However, we only really want progress bars for historical catch-ups.

    async def _reconcile_all_active_symbols(self):
        """
        Runs on startup. Checks DuckDB state, archives if needed, 
        and fetches missing data from MT5.
        """
        deps = get_current_broker_deps()
        if not deps:
            return
            
        active_symbols = deps['meta_store'].get_active_symbols()
        for symbol, timeframes in active_symbols.items():
            for tf in timeframes:
                await self.reconcile_symbol_timeframe(symbol, tf)

    async def reconcile_symbol_timeframe(self, symbol: str, timeframe: str):
        """The core reconciliation flow for a specific symbol/timeframe."""
        logger.info(f"Reconciling {symbol} {timeframe}...")
        
        deps = get_current_broker_deps()
        if not deps: return
        
        sqlite_manager = deps['sqlite_manager']
        
        # 1. MT5 Catch-up (断点续传) or Initial Sync
        if not MT5_AVAILABLE:
            logger.warning("MT5 not available. Skipping catch-up.")
            return
            
        # Use the initial sync state captured at startup to avoid race condition with live ticks
        last_sync = self._initial_sync_states.get((symbol, timeframe))
        if last_sync is None:
            last_sync = sqlite_manager.get_sync_state(symbol, timeframe)
            
        current_time = int(datetime.now().timestamp())
        
        mt5_tf = self._get_mt5_timeframe(timeframe)
        if mt5_tf is None: return
        
        def ts_to_dt(ts: int) -> datetime:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
            
        if not last_sync:
            logger.info(f"Initial sync for {symbol} {timeframe} (Last 3 months)")
            start_time = current_time - (90 * 24 * 3600)
            
            rates = await asyncio.to_thread(mt5.copy_rates_range, symbol, mt5_tf, ts_to_dt(start_time), ts_to_dt(current_time))
            
            if rates is not None and len(rates) > 0:
                bars = self._format_rates(rates, symbol, timeframe, "initial_sync")
                await sqlite_manager.upsert_bars(bars)
                sqlite_manager.update_sync_state(symbol, timeframe, int(rates[-1]['time']))
                logger.info(f"Initial sync: inserted {len(bars)} bars for {symbol} {timeframe}")
            else:
                err = mt5.last_error()
                logger.warning(f"copy_rates_range failed or returned empty for {symbol} {timeframe}. Error: {err}")
                
                rates = await asyncio.to_thread(mt5.copy_rates_from_pos, symbol, mt5_tf, 0, 50000)
                if rates is not None and len(rates) > 0:
                    bars = self._format_rates(rates, symbol, timeframe, "initial_sync_fallback")
                    await sqlite_manager.upsert_bars(bars)
                    sqlite_manager.update_sync_state(symbol, timeframe, int(rates[-1]['time']))
                    logger.info(f"Initial sync (fallback): inserted {len(bars)} bars for {symbol} {timeframe}")
                    start_time = int(rates[0]['time'])
                else:
                    logger.error(f"Initial sync complete failure for {symbol} {timeframe}. Error: {mt5.last_error()}")
                
            asyncio.create_task(self._background_historical_fetch(symbol, timeframe, start_time))
            
        else:
            if current_time - last_sync > self._tf_to_seconds(timeframe):
                logger.info(f"Fetching catch-up data for {symbol} {timeframe} from {last_sync} to {current_time}")
                await self._publish_progress(symbol, timeframe, 0, "syncing", f"Catching up {timeframe} data...")
                
                safe_last_sync = max(0, last_sync - (24 * 3600))
                rates = await asyncio.to_thread(mt5.copy_rates_range, symbol, mt5_tf, ts_to_dt(safe_last_sync), ts_to_dt(current_time))
                
                if rates is not None and len(rates) > 0:
                    bars = self._format_rates(rates, symbol, timeframe, "catchup")
                    await sqlite_manager.upsert_bars(bars)
                    sqlite_manager.update_sync_state(symbol, timeframe, int(rates[-1]['time']))
                    logger.info(f"Caught up {len(bars)} bars for {symbol} {timeframe}")
                else:
                    logger.error(f"Catch-up failed: mt5.copy_rates_range returned None or empty for {symbol} {timeframe}. Error: {mt5.last_error()}")
                
                await self._publish_progress(symbol, timeframe, 100, "completed", "Catch-up completed")

        # Background historical fetch resumption
        if last_sync:
            time_range = sqlite_manager.get_time_range(symbol, timeframe)
            min_time_sqlite = time_range.get('min_time')
            
            oldest_time = min_time_sqlite
            
            current_time = int(datetime.now().timestamp())
            target_start_time = current_time - (36 * 30 * 24 * 3600)
            
            if oldest_time and oldest_time > target_start_time + (30 * 24 * 3600):
                sync_completed_flag = sqlite_manager.get_archive_state(symbol, f"{timeframe}_sync_completed")
                
                if not sync_completed_flag:
                    logger.info(f"Resuming interrupted historical fetch for {symbol} {timeframe}. Oldest data: {datetime.fromtimestamp(oldest_time, tz=timezone.utc)}")
                    await self._publish_progress(symbol, timeframe, 0, "syncing", f"Resuming background sync for {timeframe}...")
                    asyncio.create_task(self._background_historical_fetch(symbol, timeframe, oldest_time))
                else:
                    await self._publish_progress(symbol, timeframe, 100, "completed", f"{timeframe} fully synced")
            else:
                sqlite_manager.update_archive_state(symbol, f"{timeframe}_sync_completed", "true")
                await self._publish_progress(symbol, timeframe, 100, "completed", f"{timeframe} fully synced")

    async def _background_historical_fetch(self, symbol: str, timeframe: str, end_time: int):
        """
        后台静默拉取过去 36 个月的数据并存入 SQLite。
        """
        from backend.core.message_bus import message_bus, SyncProgressMessage
        
        if not MT5_AVAILABLE: return
        
        deps = get_current_broker_deps()
        if not deps: return
        sqlite_manager = deps['sqlite_manager']
        
        logger.info(f"Starting background historical fetch for {symbol} {timeframe} (prior to {end_time})")
        
        mt5_tf = self._get_mt5_timeframe(timeframe)
        if mt5_tf is None: return
        
        def ts_to_dt(ts: int) -> datetime:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
            
        current_time = int(datetime.now().timestamp())
        
        target_start_time = current_time - (36 * 30 * 24 * 3600)
        total_time_span = end_time - target_start_time
        
        await self._publish_progress(symbol, timeframe, 0, "syncing", f"Starting background sync for {timeframe}...")
        
        current_end = end_time
        
        while current_end > target_start_time:
            current_start = current_end - (30 * 24 * 3600)
            if current_start < target_start_time:
                current_start = target_start_time
                
            dt_start = ts_to_dt(current_start)
            safe_end = current_end + 3600
            
            logger.info(f"Background fetching {symbol} {timeframe}: {dt_start.strftime('%Y-%m')}")
            
            rates = await asyncio.to_thread(mt5.copy_rates_range, symbol, mt5_tf, ts_to_dt(current_start), ts_to_dt(safe_end))
            
            if rates is not None and len(rates) > 0:
                bars = self._format_rates(rates, symbol, timeframe, "historical_sync")
                await sqlite_manager.upsert_bars(bars)
            else:
                logger.info(f"No data returned for {symbol} {timeframe} in {dt_start.strftime('%Y-%m')}")
                if timeframe in ["M1", "M5", "M15"]:
                    logger.info(f"Broker likely has no earlier data for {timeframe}. Stopping fetch early.")
                    break
                
            current_end = current_start
            
            progress_percent = int(((end_time - current_end) / total_time_span) * 100)
            await self._publish_progress(symbol, timeframe, progress_percent, "syncing", f"Syncing {timeframe}: {dt_start.strftime('%Y-%m')}")
            
            await asyncio.sleep(0.1)
            
        logger.info(f"Background historical fetch completed for {symbol} {timeframe}")
        sqlite_manager.update_archive_state(symbol, f"{timeframe}_sync_completed", "true")
        await self._publish_progress(symbol, timeframe, 100, "completed", f"{timeframe} historical sync completed")

    def _format_rates(self, rates, symbol, timeframe, source) -> List[Dict]:
        bars = []
        for r in rates:
            bars.append({
                "symbol": symbol,
                "timeframe": timeframe,
                "time": int(r['time']),
                "open": float(r['open']),
                "high": float(r['high']),
                "low": float(r['low']),
                "close": float(r['close']),
                "tick_volume": int(r['tick_volume']),
                "delta_volume": 0,
                "source": source
            })
        return bars

    def _tf_to_seconds(self, tf: str) -> int:
        mapping = {"M1": 60, "M5": 300, "M15": 900, "H1": 3600, "D1": 86400}
        return mapping.get(tf, 60)
        
    def _get_mt5_timeframe(self, tf_str: str):
        if not MT5_AVAILABLE: return None
        mapping = {
            "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15, "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1, "W1": mt5.TIMEFRAME_W1,
            "MN1": mt5.TIMEFRAME_MN1, "MN": mt5.TIMEFRAME_MN1,
        }
        return mapping.get(tf_str)

ingestion_service = IngestionService()
