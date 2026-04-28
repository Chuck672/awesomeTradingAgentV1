import glob
import logging
from typing import Any, Dict, List

from backend.core.broker_context import get_current_broker_deps

logger = logging.getLogger(__name__)


class HistoricalService:
    """
    Handles API requests for historical data by querying the unified DuckDB + Parquet layer.
    """

    def get_history(self, symbol: str, timeframe: str, before_time: int = 0, limit: int = 5000) -> List[Dict[str, Any]]:
        """
        Retrieves historical OHLCV data.
        Returns up to `limit` records, optionally filtered by `before_time` timestamp for lazy loading.
        """
        logger.info(f"Fetching history for {symbol} {timeframe}, before_time={before_time}, limit={limit}")

        deps = get_current_broker_deps()
        if not deps:
            return []

        sqlite_manager = deps["sqlite_manager"]

        hot_time_filter = f"AND time < {int(before_time)}" if int(before_time) > 0 else ""

        try:
            query = f"""
                SELECT * FROM (
                    SELECT time, open, high, low, close, tick_volume, delta_volume, source
                    FROM ohlcv
                    WHERE symbol = ? AND timeframe = ? {hot_time_filter}
                    ORDER BY time DESC
                    LIMIT {int(limit)}
                ) sub
                ORDER BY time ASC
            """
            
            with __import__('sqlite3').connect(sqlite_manager.db_path) as conn:
                import pandas as pd
                df = pd.read_sql_query(query, conn, params=(symbol, timeframe))

            if df is None or df.empty:
                return []

            df = df.drop_duplicates(subset=["time"], keep="last")
            df = df.where(df.notnull(), None)
            return df.to_dict("records")
        except Exception as e:
            logger.error(f"Error querying historical data for {symbol} {timeframe}: {e}")
            return []

    def get_history_range(
        self,
        symbol: str,
        timeframe: str,
        *,
        from_time: int,
        to_time: int,
        limit: int = 20000,
    ) -> List[Dict[str, Any]]:
        """
        获取 [from_time, to_time] 区间内的 OHLCV（按 time ASC）。
        注意：会自动合并 Parquet cold + DuckDB hot，并去重（hot 覆盖 cold）。
        """
        deps = get_current_broker_deps()
        if not deps:
            return []

        sqlite_manager = deps["sqlite_manager"]

        frm = int(from_time)
        to = int(to_time)
        if frm <= 0 or to <= 0 or frm > to:
            return []

        try:
            query = f"""
                SELECT * FROM (
                    SELECT time, open, high, low, close, tick_volume, delta_volume, source
                    FROM ohlcv
                    WHERE symbol = ? AND timeframe = ? AND time >= {frm} AND time <= {to}
                    ORDER BY time ASC
                    LIMIT {int(limit)}
                ) sub
                ORDER BY time ASC
            """
            with __import__('sqlite3').connect(sqlite_manager.db_path) as conn:
                import pandas as pd
                df = pd.read_sql_query(query, conn, params=(symbol, timeframe))

            if df is None or df.empty:
                return []

            df = df.drop_duplicates(subset=["time"], keep="last")
            df = df.where(df.notnull(), None)
            return df.to_dict("records")
        except Exception as e:
            logger.error(f"Error querying range data for {symbol} {timeframe}: {e}")
            return []


historical_service = HistoricalService()

