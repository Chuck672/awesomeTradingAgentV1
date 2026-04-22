import sqlite3

def inspect_timeframes():
    conn = sqlite3.connect('market_data.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT DISTINCT timeframe FROM ohlcv_data;")
    tfs = cursor.fetchall()
    print("Timeframes:", tfs)
    
    for tf in tfs:
        cursor.execute(f"SELECT COUNT(*) FROM ohlcv_data WHERE timeframe='{tf[0]}';")
        count = cursor.fetchone()[0]
        print(f"Count for {tf[0]}: {count}")

if __name__ == '__main__':
    inspect_timeframes()
