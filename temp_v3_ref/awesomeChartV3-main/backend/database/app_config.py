import sqlite3
import json
from typing import List, Dict, Optional
import os
import logging
import platform

logger = logging.getLogger(__name__)

class AppConfigStore:
    """
    Manages global application configuration, external data paths,
    and configured MT5 brokers.
    """
    def __init__(self):
        self.base_dir = self._get_default_base_dir()
        os.makedirs(self.base_dir, exist_ok=True)
        self.db_path = os.path.join(self.base_dir, "app_config.sqlite")
        self._init_db()

    def _get_default_base_dir(self) -> str:
        """Calculate the OS-specific application data directory."""
        # 允许通过环境变量覆盖数据目录（便于本地/测试环境接入离线历史数据集）
        override = os.environ.get("AWESOMECHART_DATA_DIR", "").strip()
        if override:
            return override

        # 约定：如果工作区存在 /workspace/historyData/data（例如用户提供的 historyData.zip 解压后），优先使用它
        # 这样即便没有连接 broker，也能直接读取 parquet 历史数据进行测试。
        workspace_dataset = "/workspace/historyData/data"
        if os.path.exists(os.path.join(workspace_dataset, "app_config.sqlite")):
            return workspace_dataset

        system = platform.system()
        if system == "Windows":
            appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
            return os.path.join(appdata, "AwesomeChart", "data")
        elif system == "Darwin": # macOS
            return os.path.join(os.path.expanduser("~"), "Library", "Application Support", "AwesomeChart", "data")
        else: # Linux / other
            return os.path.join(os.path.expanduser("~"), ".config", "AwesomeChart", "data")

    def get_base_dir(self) -> str:
        return self.base_dir
        
    def get_brokers_dir(self) -> str:
        brokers_dir = os.path.join(self.base_dir, "brokers")
        os.makedirs(brokers_dir, exist_ok=True)
        return brokers_dir

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Table for configured brokers
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS brokers (
                    id TEXT PRIMARY KEY,
                    server TEXT,
                    login TEXT,
                    path TEXT,
                    is_active INTEGER DEFAULT 0
                )
            """)
            conn.commit()

    def add_broker(self, server: str, login: str, path: str = "") -> str:
        """Add or update a broker configuration. Returns the broker_id."""
        # Sanitize login for directory name (it could be empty)
        safe_login = login if login else "default"
        # Sanitize server name for directory
        safe_server = "".join([c if c.isalnum() else "_" for c in server])
        broker_id = f"{safe_server}_{safe_login}"
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO brokers (id, server, login, path, is_active)
                VALUES (?, ?, ?, ?, 0)
                ON CONFLICT(id) DO UPDATE SET 
                    server=excluded.server, 
                    login=excluded.login,
                    path=excluded.path
            """, (broker_id, server, login, path))
            conn.commit()
            
        return broker_id

    def set_active_broker(self, broker_id: str):
        """Set a specific broker as active, deactivate others."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE brokers SET is_active = 0")
            cursor.execute("UPDATE brokers SET is_active = 1 WHERE id = ?", (broker_id,))
            conn.commit()

    def get_active_broker(self) -> Optional[Dict]:
        """Get the currently active broker configuration."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, server, login, path FROM brokers WHERE is_active = 1")
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "server": row[1],
                    "login": row[2],
                    "path": row[3]
                }
            return None
            
    def get_all_brokers(self) -> List[Dict]:
        """Get all configured brokers."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, server, login, path, is_active FROM brokers")
            rows = cursor.fetchall()
            return [
                {
                    "id": r[0],
                    "server": r[1],
                    "login": r[2],
                    "path": r[3],
                    "is_active": bool(r[4])
                } for r in rows
            ]

app_config = AppConfigStore()
