import logging
from typing import Dict, Any, Optional

from backend.database.app_config import app_config
from backend.database.sqlite_manager import SQLiteManager

logger = logging.getLogger(__name__)

# Global dictionary to cache instantiated services per broker
_broker_contexts: Dict[str, Dict[str, Any]] = {}

def get_broker_context(broker_id: str) -> Dict[str, Any]:
    """Get or create the storage instances for a specific broker."""
    if broker_id not in _broker_contexts:
        logger.info(f"Initializing storage context for broker: {broker_id}")
        sqlite_mgr = SQLiteManager(broker_id)
        
        # We will dynamically import ingestion_service and historical_service
        # to avoid circular imports. But those services also need to be broker-aware.
        
        _broker_contexts[broker_id] = {
            "sqlite_manager": sqlite_mgr,
            # We keep these aliases for backwards compatibility temporarily
            # if we didn't fully update all usages, but let's change them all!
            "meta_store": sqlite_mgr,
            "duckdb_manager": sqlite_mgr
        }
        
    return _broker_contexts[broker_id]

def get_current_broker_deps() -> Optional[Dict[str, Any]]:
    """Get the currently active broker's dependencies."""
    active_broker = app_config.get_active_broker()
    if not active_broker:
        return None
    return get_broker_context(active_broker["id"])
