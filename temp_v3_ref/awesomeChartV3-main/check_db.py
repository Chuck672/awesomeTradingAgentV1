import sqlite3
import os

db_path = os.path.join('symbol_data', 'XAUUSDz.db')
print("DB Path:", db_path)
print("Exists:", os.path.exists(db_path))
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    print("Tables in XAUUSDz.db:", cursor.fetchall())
    conn.close()
