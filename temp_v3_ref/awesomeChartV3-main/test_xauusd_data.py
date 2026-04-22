from backend.database.app_config import app_config
import duckdb
import os
import pandas as pd

broker_id = "Exness_MT5Real5_default"
db_path = os.path.join(app_config.get_brokers_dir(), broker_id, "hot_data.duckdb")

conn = duckdb.connect(db_path, read_only=True)

symbol = "XAUUSDz"
timeframe = "H1"
limit = 5000

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

df = conn.execute(query, (symbol, timeframe)).df()
df = df.drop_duplicates(subset=['time'], keep='last')

# Check if sorted
if not df['time'].is_monotonic_increasing:
    print("Data is NOT monotonic increasing!")
    # Find out of order
    diffs = df['time'].diff()
    print(df[diffs < 0])
else:
    print("Data is monotonic increasing.")

# Check for gaps
diffs = df['time'].diff()
print(f"Max gap: {diffs.max() / 3600} hours")
if diffs.max() > 24 * 7 * 3600:
    print(df[diffs > 24 * 7 * 3600])

print("Done")
