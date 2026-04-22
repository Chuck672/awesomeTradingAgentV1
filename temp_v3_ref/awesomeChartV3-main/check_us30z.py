from backend.api.dependencies import get_current_broker_deps
from backend.database.app_config import app_config
import os
import glob

deps = get_current_broker_deps()
duckdb_manager = deps['duckdb_manager']

print("--- DuckDB Data for US30z H1 ---")
try:
    res = duckdb_manager.conn.execute("SELECT MIN(time), MAX(time), COUNT(*) FROM ohlcv_hot WHERE symbol='US30z' AND timeframe='H1'").fetchone()
    print(f"Min time: {res[0]}, Max time: {res[1]}, Count: {res[2]}")
except Exception as e:
    print(f"Error querying DuckDB: {e}")

print("--- Parquet Files for US30z H1 ---")
parquet_dir = os.path.join(app_config.get_brokers_dir(), deps['meta_store'].broker_id, "parquet", "US30z", "H1")
print(f"Parquet Dir: {parquet_dir}")
files = glob.glob(os.path.join(parquet_dir, "*.parquet"))
print(f"Found {len(files)} parquet files")
for f in files:
    try:
        res = duckdb_manager.conn.execute(f"SELECT MIN(time), MAX(time), COUNT(*) FROM read_parquet('{f}')").fetchone()
        print(f"File {os.path.basename(f)}: Min time: {res[0]}, Max time: {res[1]}, Count: {res[2]}")
    except Exception as e:
        print(f"Error reading {f}: {e}")

