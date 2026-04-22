import asyncio
import sqlite3
import os
import sys

# Ensure backend can be imported
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.database.agent_db import get_checkpointer, get_agent_db_path

async def main():
    db_path = get_agent_db_path()
    print(f"[*] Agent Sandbox DB Path: {db_path}")
    
    # 1. Initialize and run setup
    try:
        async with get_checkpointer() as saver:
            print("[*] Successfully initialized AsyncSqliteSaver and ran setup().")
    except Exception as e:
        print(f"[!] Error during AsyncSqliteSaver setup: {e}")
        return

    # 2. Verify tables were created correctly
    if not os.path.exists(db_path):
        print("[!] Verification FAILED: Database file was not created.")
        return
        
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]
            print(f"[*] Found tables in DB: {tables}")
            
            if "checkpoints" in tables:
                print("[*] Verification PASSED: 'checkpoints' table exists!")
            else:
                print("[!] Verification FAILED: 'checkpoints' table is missing.")
    except Exception as e:
        print(f"[!] Error verifying database tables: {e}")

if __name__ == "__main__":
    asyncio.run(main())
