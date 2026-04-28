import sys
import os
import copy

# Ensure the root directory is in the path
if getattr(sys, 'frozen', False):
    # If the application is run as a bundle, the PyInstaller bootloader
    # extends the sys.path to include the bundle directory.
    pass
else:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn
import uvicorn.config

def _build_log_config():
    cfg = copy.deepcopy(uvicorn.config.LOGGING_CONFIG)
    cfg.setdefault("root", {"handlers": ["default"], "level": "INFO"})
    cfg.setdefault("filters", {})
    cfg["filters"]["suppress_alerts_access"] = {
        "()": "backend.logging_filters.SuppressAlertsAccessLogFilter"
    }
    access = cfg.get("handlers", {}).get("access")
    if isinstance(access, dict):
        access.setdefault("filters", [])
        if "suppress_alerts_access" not in access["filters"]:
            access["filters"].append("suppress_alerts_access")
    cfg.setdefault("loggers", {})
    cfg["loggers"].setdefault("watchfiles", {})["level"] = "WARNING"
    cfg["loggers"].setdefault("watchfiles.main", {})["level"] = "WARNING"
    cfg["loggers"].setdefault("backend.services.ingestion", {})["level"] = "WARNING"
    cfg["loggers"].setdefault("backend.api.websocket", {})["level"] = "INFO"
    cfg["loggers"].setdefault("backend.services.alerts_engine", {})["level"] = "INFO"
    cfg["loggers"].setdefault("backend.api.agent_routes", {})["level"] = "INFO"
    cfg["loggers"].setdefault("backend.core.message_bus", {})["level"] = "INFO"
    cfg["loggers"].setdefault("backend.services.telegram", {})["level"] = "INFO"
    return cfg

if __name__ == "__main__":
    from backend.core.arch_check import check_no_services_import_api

    check_no_services_import_api()
    log_config = _build_log_config()
    if getattr(sys, 'frozen', False):
        from backend.main import app

        # Disable reload when running from the compiled executable
        uvicorn.run(app, host="0.0.0.0", port=8123, log_config=log_config, access_log=False)
    else:
        uvicorn.run(
            "backend.main:app",
            host="0.0.0.0",
            port=8123,
            reload=True,
            log_config=log_config,
            access_log=False,
        )
