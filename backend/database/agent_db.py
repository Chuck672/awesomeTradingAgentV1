import os
from contextlib import asynccontextmanager
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from backend.database.app_config import app_config

def get_agent_db_path() -> str:
    """Returns the absolute path to the isolated agent sandbox database."""
    return os.path.join(app_config.get_base_dir(), "agent_sandbox.sqlite")

@asynccontextmanager
async def get_checkpointer():
    """
    Yields an initialized AsyncSqliteSaver connected to the agent sandbox database.
    It automatically calls setup() to ensure the checkpoint tables exist.
    """
    db_path = get_agent_db_path()
    async with AsyncSqliteSaver.from_conn_string(db_path) as saver:
        await saver.setup()
        yield saver
