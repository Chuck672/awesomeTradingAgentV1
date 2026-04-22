import sqlite3

def inspect_db():
    conn = sqlite3.connect('market_data.db')
    cursor = conn.cursor()
    
    # Get all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print("Tables:", tables)
    
    # For each table, get schema and a few sample rows
    for table_name in tables:
        name = table_name[0]
        print(f"\n--- Table: {name} ---")
        
        cursor.execute(f"PRAGMA table_info({name});")
        columns = cursor.fetchall()
        print("Columns:")
        for col in columns:
            print(f"  {col[1]} ({col[2]})")
            
        cursor.execute(f"SELECT * FROM {name} LIMIT 5;")
        rows = cursor.fetchall()
        print("Sample Data:")
        for row in rows:
            print(f"  {row}")

if __name__ == '__main__':
    inspect_db()
