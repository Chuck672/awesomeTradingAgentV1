import logging
from typing import Any, Dict, Optional

from backend.database.app_config import app_config
from backend.database.sqlite_manager import SQLiteManager

logger = logging.getLogger(__name__)

_broker_contexts: Dict[str, Dict[str, Any]] = {}


def get_broker_context(broker_id: str) -> Dict[str, Any]:
    if broker_id not in _broker_contexts:
        logger.info(f"Initializing storage context for broker: {broker_id}")
        sqlite_mgr = SQLiteManager(broker_id)

        _broker_contexts[broker_id] = {
            "sqlite_manager": sqlite_mgr,
            "meta_store": sqlite_mgr,
            "duckdb_manager": sqlite_mgr,
        }

    return _broker_contexts[broker_id]


def get_current_broker_deps() -> Optional[Dict[str, Any]]:
    active_broker = app_config.get_active_broker()
    if not active_broker:
        return None
    return get_broker_context(active_broker["id"])

