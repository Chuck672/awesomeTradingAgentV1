import os
import shutil
import sqlite3
from backend.database.app_config import app_config

broker_id = "Exness_MT5Real5_default"
sandbox_dir = os.path.join(app_config.get_brokers_dir(), broker_id)
meta_db_path = os.path.join(sandbox_dir, "meta.sqlite")
hot_db_path = os.path.join(sandbox_dir, "hot_data.duckdb")

def clear_symbol(symbol: str):
    print(f"Clearing corrupted data for {symbol}...")
    
    # 1. Clear Parquet files
    parquet_dir = os.path.join(sandbox_dir, "parquet", symbol)
    if os.path.exists(parquet_dir):
        shutil.rmtree(parquet_dir)
        print(f"Deleted parquet directory: {parquet_dir}")

    # 2. Clear from SQLite meta
    with sqlite3.connect(meta_db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sync_state WHERE symbol = ?", (symbol,))
        conn.commit()
        print(f"Cleared sync state for {symbol}")

    # 3. Clear from DuckDB hot data
    import duckdb
    conn = duckdb.connect(hot_db_path, read_only=False)
    conn.execute("DELETE FROM ohlcv_hot WHERE symbol = ?", (symbol,))
    conn.close()
    print(f"Deleted {symbol} from DuckDB hot data")

clear_symbol("US30z")
clear_symbol("XAUUSDz")
print("\nDone! Please restart the backend. The data will be freshly fetched.")
