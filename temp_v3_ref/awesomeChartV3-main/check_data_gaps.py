import os
import duckdb
import sqlite3
from datetime import datetime, timezone
import pandas as pd

def run_gap_analysis():
    appdata_dir = os.path.expandvars(r"%APPDATA%\AwesomeChart\data")
    config_db = os.path.join(appdata_dir, "app_config.sqlite")

    if not os.path.exists(config_db):
        print(f"Config DB not found.")
        return

    conn = sqlite3.connect(config_db)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM brokers WHERE is_active = 1")
    row = cursor.fetchone()
    if not row:
        print("No active broker found.")
        return
    broker_id = row[0]

    parquet_dir = os.path.join(appdata_dir, "brokers", broker_id, "parquet")
    if not os.path.exists(parquet_dir):
        print("Parquet dir not found.")
        return

    db = duckdb.connect()
    
    tf_to_seconds = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "D1": 86400}
    
    print(f"Running Gap Analysis for Broker: {broker_id}...")
    
    symbols = os.listdir(parquet_dir)
    for sym in symbols:
        sym_dir = os.path.join(parquet_dir, sym)
        if not os.path.isdir(sym_dir): continue
        for tf in os.listdir(sym_dir):
            tf_dir = os.path.join(sym_dir, tf)
            if not os.path.isdir(tf_dir): continue
            
            try:
                # Calculate gaps by using window functions to find difference between current and next row
                query = f"""
                    WITH ordered AS (
                        SELECT time,
                               LEAD(time) OVER (ORDER BY time) as next_time
                        FROM read_parquet('{tf_dir}/*.parquet')
                    )
                    SELECT time, next_time, (next_time - time) as diff
                    FROM ordered
                    WHERE diff > ?
                """
                
                # We expect normal gaps over weekends (2 days = 172800 seconds).
                # So any gap > 3 days (259200 seconds) is a true data gap.
                gap_threshold = 259200 
                if tf in ["W1", "MN1", "MN"]:
                    gap_threshold = 86400 * 35 # larger for W1, MN
                
                df = db.execute(query, (gap_threshold,)).df()
                
                if df.empty:
                    print(f"[{sym} | {tf}] No abnormal gaps found (Threshold: {gap_threshold}s)")
                else:
                    print(f"[{sym} | {tf}] Found {len(df)} abnormal gaps!")
                    for _, row in df.head(5).iterrows():
                        t1 = datetime.fromtimestamp(row['time'], tz=timezone.utc).strftime('%Y-%m-%d %H:%M')
                        t2 = datetime.fromtimestamp(row['next_time'], tz=timezone.utc).strftime('%Y-%m-%d %H:%M')
                        print(f"   -> Gap: {t1} to {t2} (Diff: {row['diff']}s)")
                    if len(df) > 5:
                        print(f"   -> ... and {len(df) - 5} more gaps.")
                        
            except Exception as e:
                print(f"[{sym} | {tf}] Error querying parquet: {e}")

if __name__ == "__main__":
    run_gap_analysis()