import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio

from backend.api.routes import router as api_router
from backend.api.websocket import router as ws_router
from backend.api.websocket import start_ws_subscription
from backend.api.agent_routes import router as agent_router
from backend.core.message_bus import message_bus
from backend.data_sources.mt5_source import mt5_source
from backend.services.ingestion import ingestion_service
from backend.services.research.job_store import job_store

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize services
    print("Starting up backend services...")
    
    # Start the message bus first
    await message_bus.start()
    
    # Start WebSocket subscription to message bus
    await start_ws_subscription()
    
    # Start the MT5 data source (it will connect to active broker if available)
    from backend.database.app_config import app_config
    active_broker = app_config.get_active_broker()
    if active_broker:
        print(f"Connecting to active broker: {active_broker['server']}")
        # Run synchronous connect_broker in a separate thread to prevent blocking the asyncio event loop
        await asyncio.to_thread(
            mt5_source.connect_broker,
            active_broker['server'],
            active_broker['login'],
            active_broker['path']
        )
        
    await mt5_source.start()
    
    # Start the Ingestion Service
    await ingestion_service.start()

    # Background: cleanup finished research jobs periodically
    async def _job_cleanup_loop():
        while True:
            try:
                # 清理 3 小时前结束的任务
                job_store.cleanup(max_age_sec=3 * 3600)
            except Exception:
                pass
            await asyncio.sleep(600)

    cleanup_task = asyncio.create_task(_job_cleanup_loop())

    # Background: alerts engine (MVP)
    from backend.services.alerts_engine import loop as alerts_loop
    alerts_task = asyncio.create_task(alerts_loop(30))
    
    yield
    
    # Shutdown: Clean up services
    print("Shutting down backend services...")
    cleanup_task.cancel()
    alerts_task.cancel()
    await mt5_source.stop()
    await ingestion_service.stop()
    await message_bus.stop()

app = FastAPI(title="OrderFlowChart Backend API", lifespan=lifespan)

# Allow CORS for local frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")
app.include_router(ws_router, prefix="/api")
app.include_router(agent_router, prefix="/api/agent")

if __name__ == "__main__":
    import uvicorn
    import sys
    # If running as PyInstaller executable, disable reload and pass app directly
    if getattr(sys, 'frozen', False):
        uvicorn.run(app, host="0.0.0.0", port=8123)
    else:
        uvicorn.run("backend.main:app", host="0.0.0.0", port=8123, reload=True)

