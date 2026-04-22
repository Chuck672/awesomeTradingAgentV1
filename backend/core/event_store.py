import sqlite3
import json
import logging
import os
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class EventStore:
    """
    Append-only event store for recording raw market events (ZMQ and Poll).
    This allows for local playback, auditing, and debugging of the ingestion pipeline.
    """
    def __init__(self, db_path: str = "data/events.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS market_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT,
                    payload TEXT, -- JSON string
                    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def record_event(self, topic: str, payload: Dict[str, Any]):
        """
        Record a single raw event.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO market_events (topic, payload)
                    VALUES (?, ?)
                """, (topic, json.dumps(payload)))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to record event to EventStore: {e}")

    def fetch_events(self, topic: str = None, limit: int = 1000, offset: int = 0) -> List[Dict]:
        """
        Retrieve recorded events, useful for ReplayService.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if topic:
                cursor.execute("""
                    SELECT id, topic, payload, received_at FROM market_events 
                    WHERE topic = ? ORDER BY id ASC LIMIT ? OFFSET ?
                """, (topic, limit, offset))
            else:
                cursor.execute("""
                    SELECT id, topic, payload, received_at FROM market_events 
                    ORDER BY id ASC LIMIT ? OFFSET ?
                """, (limit, offset))
            
            rows = cursor.fetchall()
            events = []
            for r in rows:
                event = dict(r)
                try:
                    event['payload'] = json.loads(event['payload'])
                except:
                    pass
                events.append(event)
            return events

event_store = EventStore()
