import sqlite3
import duckdb
import os
import glob
from datetime import datetime, timezone

def run_tests():
    appdata_dir = os.path.expandvars(r"%APPDATA%\AwesomeChart\data")
    config_db = os.path.join(appdata_dir, "app_config.sqlite")

    if not os.path.exists(config_db):
        print(f"Config DB not found: {config_db}")
        return

    conn = sqlite3.connect(config_db)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM brokers WHERE is_active = 1")
    row = cursor.fetchone()
    if not row:
        print("No active broker found.")
        return
    broker_id = row[0]
    print(f"Active Broker: {broker_id}")

    duckdb_path = os.path.join(appdata_dir, "brokers", broker_id, "hot_data.duckdb")
    parquet_dir = os.path.join(appdata_dir, "brokers", broker_id, "parquet")

    print("\n================ DuckDB Analysis ================")
    if not os.path.exists(duckdb_path):
        print(f"DuckDB not found at {duckdb_path}")
    else:
        db = duckdb.connect(duckdb_path)
        try:
            df = db.execute("SELECT symbol, timeframe, MIN(time) as min_t, MAX(time) as max_t, COUNT(*) as cnt FROM ohlcv_hot GROUP BY symbol, timeframe").df()
            if df.empty:
                print("DuckDB is empty.")
            for _, row in df.iterrows():
                min_dt = datetime.fromtimestamp(row['min_t'], tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
                max_dt = datetime.fromtimestamp(row['max_t'], tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
                print(f"[{row['symbol']} | {row['timeframe']}] Count: {row['cnt']}, Start: {min_dt}, End: {max_dt}")
        except Exception as e:
            print("DuckDB query error:", e)

    print("\n================ Parquet Analysis ===============")
    if not os.path.exists(parquet_dir):
        print(f"Parquet dir not found at {parquet_dir}")
    else:
        symbols = os.listdir(parquet_dir)
        for sym in symbols:
            sym_dir = os.path.join(parquet_dir, sym)
            if not os.path.isdir(sym_dir): continue
            for tf in os.listdir(sym_dir):
                tf_dir = os.path.join(sym_dir, tf)
                if not os.path.isdir(tf_dir): continue
                files = glob.glob(os.path.join(tf_dir, "*.parquet"))
                print(f"[{sym} | {tf}] Parquet files count: {len(files)}")
                if files:
                    try:
                        db = duckdb.connect()
                        query = f"SELECT MIN(time) as min_t, MAX(time) as max_t, COUNT(*) as cnt FROM read_parquet('{tf_dir}/*.parquet')"
                        df = db.execute(query).df()
                        min_dt = datetime.fromtimestamp(df['min_t'][0], tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
                        max_dt = datetime.fromtimestamp(df['max_t'][0], tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
                        print(f"   -> Total Rows: {df['cnt'][0]}, Start: {min_dt}, End: {max_dt}")
                    except Exception as e:
                        print("   -> Error reading parquet:", e)

if __name__ == "__main__":
    run_tests()
