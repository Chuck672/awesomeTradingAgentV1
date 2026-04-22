import sqlite3
import os

def check_db(symbol):
    db_path = os.path.join('symbol_data', f'{symbol}.db')
    print(f"--- Checking {db_path} ---")
    if not os.path.exists(db_path):
        print(f"File {db_path} does not exist.")
        return
        
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print(f"Tables in {symbol}.db:", tables)
        
        if ('ohlcv_data',) in tables:
            cursor.execute("PRAGMA table_info(ohlcv_data);")
            columns = cursor.fetchall()
            print("Columns in ohlcv_data:")
            for col in columns:
                print(f"  {col[1]} ({col[2]})")
            
            cursor.execute("SELECT COUNT(*) FROM ohlcv_data;")
            count = cursor.fetchone()[0]
            print(f"Row count in ohlcv_data: {count}")
        else:
            print("WARNING: Table 'ohlcv_data' is MISSING in this database.")
            
        conn.close()
    except Exception as e:
        print(f"Error reading DB: {e}")

if __name__ == '__main__':
    check_db('XAUUSD')
    print("\n")
    check_db('XAUUSDz')
