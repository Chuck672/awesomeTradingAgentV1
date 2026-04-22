from backend.api.dependencies import get_current_broker_deps
from backend.database.app_config import app_config
import duckdb
import glob
import os

broker_id = "Exness_MT5Real5_default"
db_path = os.path.join(app_config.get_brokers_dir(), broker_id, "hot_data.duckdb")

conn = duckdb.connect(db_path, read_only=True)

symbol = "US30z"
timeframe = "H1"
limit = 5000
before_time = 0

parquet_glob = os.path.join(app_config.get_brokers_dir(), broker_id, "parquet", symbol, timeframe, "*.parquet").replace("\\", "/")

query = f"""
    SELECT * FROM (
        SELECT time, open, high, low, close, tick_volume, delta_volume, source 
        FROM read_parquet('{parquet_glob}')
        UNION ALL
        SELECT time, open, high, low, close, tick_volume, delta_volume, source 
        FROM ohlcv_hot
        WHERE symbol = ? AND timeframe = ?
        ORDER BY time DESC
        LIMIT {limit}
    ) sub
    ORDER BY time ASC
"""

try:
    df = conn.execute(query, (symbol, timeframe)).df()
    print(f"US30z count: {len(df)}")
    if len(df) > 0:
        print(f"US30z first time: {df.iloc[0]['time']}, last time: {df.iloc[-1]['time']}")
except Exception as e:
    print(f"US30z Error: {e}")

symbol = "XAUUSDz"
parquet_glob = os.path.join(app_config.get_brokers_dir(), broker_id, "parquet", symbol, timeframe, "*.parquet").replace("\\", "/")

query = f"""
    SELECT * FROM (
        SELECT time, open, high, low, close, tick_volume, delta_volume, source 
        FROM read_parquet('{parquet_glob}')
        UNION ALL
        SELECT time, open, high, low, close, tick_volume, delta_volume, source 
        FROM ohlcv_hot
        WHERE symbol = ? AND timeframe = ?
        ORDER BY time DESC
        LIMIT {limit}
    ) sub
    ORDER BY time ASC
"""
try:
    df = conn.execute(query, (symbol, timeframe)).df()
    print(f"XAUUSDz count: {len(df)}")
    if len(df) > 0:
        print(f"XAUUSDz first time: {df.iloc[0]['time']}, last time: {df.iloc[-1]['time']}")
except Exception as e:
    print(f"XAUUSDz Error: {e}")
