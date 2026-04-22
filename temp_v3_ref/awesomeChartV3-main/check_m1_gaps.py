import os
import duckdb
from backend.database.app_config import app_config
from datetime import datetime, timezone

broker_id = "Exness_MT5Real5_default"
sandbox_dir = os.path.join(app_config.get_brokers_dir(), broker_id)
db_path = os.path.join(sandbox_dir, "hot_data.duckdb")

if not os.path.exists(db_path):
    print(f"DB not found: {db_path}")
    exit(1)

conn = duckdb.connect(db_path, read_only=True)

symbols = ["XAUUSDz", "US30z"]
timeframes = ["M1", "M5"]

for symbol in symbols:
    for tf in timeframes:
        print(f"\n--- Checking {symbol} {tf} ---")
        df = conn.execute(f"""
            SELECT time 
            FROM ohlcv_hot 
            WHERE symbol = '{symbol}' AND timeframe = '{tf}'
            ORDER BY time ASC
        """).df()
        
        if len(df) == 0:
            print("No data found.")
            continue
            
        print(f"Total rows: {len(df)}")
        df['diff'] = df['time'].diff()
        
        # For M1, expected diff is 60. For M5, 300.
        # But MT5 doesn't generate bars for minutes with zero ticks.
        # Still, large gaps during active market hours (e.g. 14:00-14:30) are suspicious.
        expected_diff = 60 if tf == "M1" else 300
        # Let's flag gaps > 5 times the expected diff
        threshold = expected_diff * 5
        
        gaps = df[df['diff'] > threshold].copy()
        if len(gaps) == 0:
            print(f"No huge gaps (> {threshold}s) found.")
        else:
            print(f"Found {len(gaps)} huge gaps:")
            # Just print the last 10 gaps
            for idx, row in gaps.tail(10).iterrows():
                gap_seconds = int(row['diff'])
                end_time = int(row['time'])
                start_time = end_time - gap_seconds
                dt_start = datetime.fromtimestamp(start_time, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
                dt_end = datetime.fromtimestamp(end_time, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
                print(f"  Gap: {gap_seconds}s ({gap_seconds/60:.1f} mins) from {dt_start} to {dt_end}")

conn.close()
