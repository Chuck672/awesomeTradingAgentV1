import os
import duckdb
from backend.database.app_config import app_config
import MetaTrader5 as mt5
from datetime import datetime, timezone
import sys
import time

broker_id = "Exness_MT5Real5_default"
sandbox_dir = os.path.join(app_config.get_brokers_dir(), broker_id)
db_path = os.path.join(sandbox_dir, "hot_data.duckdb")

if not os.path.exists(db_path):
    print(f"DB not found: {db_path}")
    sys.exit(1)

if not mt5.initialize():
    print("initialize() failed")
    mt5.shutdown()
    sys.exit(1)

conn = duckdb.connect(db_path, read_only=False)

def ts_to_dt(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc)

tf_map = {
    "M1": (mt5.TIMEFRAME_M1, 60),
    "M5": (mt5.TIMEFRAME_M5, 300),
    "M15": (mt5.TIMEFRAME_M15, 900),
    "M30": (mt5.TIMEFRAME_M30, 1800),
    "H1": (mt5.TIMEFRAME_H1, 3600),
    "H4": (mt5.TIMEFRAME_H4, 14400),
    "D1": (mt5.TIMEFRAME_D1, 86400)
}

symbols = ["XAUUSDz", "US30z"]

for symbol in symbols:
    for tf, (mt5_tf, expected_diff) in tf_map.items():
        print(f"\n--- Repairing {symbol} {tf} ---")
        df = conn.execute(f"SELECT time FROM ohlcv_hot WHERE symbol = '{symbol}' AND timeframe = '{tf}' ORDER BY time ASC").df()
        
        if len(df) == 0:
            continue
            
        df['diff'] = df['time'].diff()
        
        # 10 times the expected diff is a definite gap (ignoring weekends which are ~48h)
        # Weekends are 48h = 172800s. Let's flag any gap > expected_diff * 5
        threshold = expected_diff * 5
        gaps = df[df['diff'] > threshold].copy()
        
        total_inserted = 0
        
        for idx, row in gaps.iterrows():
            gap_seconds = int(row['diff'])
            # Ignore huge gaps > 100 days (probably initial fetch boundaries)
            if gap_seconds > 100 * 24 * 3600:
                continue
                
            end_time = int(row['time'])
            start_time = end_time - gap_seconds
            
            print(f"  Fetching gap: {datetime.fromtimestamp(start_time, tz=timezone.utc)} to {datetime.fromtimestamp(end_time, tz=timezone.utc)}")
            
            # Fetch from MT5
            rates = mt5.copy_rates_range(symbol, mt5_tf, ts_to_dt(start_time), ts_to_dt(end_time))
            if rates is not None and len(rates) > 0:
                records = [
                    (
                        symbol, tf, int(r['time']),
                        float(r['open']), float(r['high']), float(r['low']), float(r['close']),
                        int(r['tick_volume']), 0, "repair"
                    ) for r in rates
                ]
                
                stmt = """
                    INSERT INTO ohlcv_hot (symbol, timeframe, time, open, high, low, close, tick_volume, delta_volume, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (symbol, timeframe, time) DO UPDATE SET 
                        open=EXCLUDED.open,
                        high=EXCLUDED.high,
                        low=EXCLUDED.low,
                        close=EXCLUDED.close,
                        tick_volume=EXCLUDED.tick_volume
                """
                conn.executemany(stmt, records)
                total_inserted += len(records)
                print(f"  -> Repaired {len(records)} bars.")
            
            time.sleep(0.1)
            
        if total_inserted > 0:
            print(f"Successfully repaired {total_inserted} total missing bars for {symbol} {tf}.")
        else:
            print("No actionable gaps found or repaired.")

conn.close()
mt5.shutdown()
print("\nRepair complete!")
