import logging
import os
from typing import List, Dict, Any
import duckdb

logger = logging.getLogger(__name__)

class FeatureService:
    """
    Scaffold for future Feature Engineering pipelines.
    Designed to compute indicators (MA, RSI, Volume Profile) over historical Parquet data,
    and cache the results in separate Parquet files for AI Bots.
    """
    def __init__(self, cache_dir: str = "data/features"):
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)
        
    def compute_and_cache(self, symbol: str, timeframe: str, feature_name: str) -> str:
        """
        Compute a specific feature over the entire dataset and save it to Parquet.
        Returns the path to the cached feature file.
        """
        from backend.core.broker_context import get_current_broker_deps
        deps = get_current_broker_deps()
        if not deps: return ""
        sqlite_manager = deps['sqlite_manager']
        
        feature_path = os.path.join(self.cache_dir, f"{symbol}_{timeframe}_{feature_name}.parquet")
        
        logger.info(f"Computing feature {feature_name} for {symbol} {timeframe}")
        
        try:
            import pandas as pd
            import sqlite3
            query = f"""
                SELECT time, close as {feature_name}
                FROM ohlcv WHERE symbol = ? AND timeframe = ?
                ORDER BY time ASC
            """
            with sqlite3.connect(sqlite_manager.db_path) as conn:
                df = pd.read_sql_query(query, conn, params=(symbol, timeframe))
                
            df.to_parquet(feature_path, compression='zstd')
            
            logger.info(f"Feature {feature_name} cached at {feature_path}")
            return feature_path
        except Exception as e:
            logger.error(f"Error computing feature {feature_name}: {e}")
            return ""

    def get_features(self, symbol: str, timeframe: str, feature_names: List[str], since: int = 0) -> List[Dict[str, Any]]:
        """
        Retrieve computed features from cache, joined by time.
        """
        from backend.core.broker_context import get_current_broker_deps
        deps = get_current_broker_deps()
        if not deps: return []
        sqlite_manager = deps['sqlite_manager']
        
        # Load hot data (already includes what used to be duckdb + parquet)
        # Note: the `fetch_hot_data` method on sqlite_manager fetches everything from `since`.
        hot_data = sqlite_manager.fetch_hot_data(symbol, timeframe, since=since)
        
        if not hot_data:
            return []
            
        return hot_data

feature_service = FeatureService()
