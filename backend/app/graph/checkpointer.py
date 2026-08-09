"""Lifecycle management for the LangGraph Postgres checkpointer.

AsyncPostgresSaver.from_conn_string() is an async context manager, not a plain
constructor (confirmed against the installed langgraph-checkpoint-postgres
package) — it must be entered once and kept open for the app's lifetime, then
exited on shutdown. A module-level singleton is enough here since Phase 1 runs
a single uvicorn process (no multi-worker deployment yet).
"""

from contextlib import AbstractAsyncContextManager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.config import get_settings

_saver_cm: AbstractAsyncContextManager | None = None
_saver: AsyncPostgresSaver | None = None


def _psycopg_dsn(database_url: str) -> str:
    """AsyncPostgresSaver connects via raw psycopg, not SQLAlchemy — it wants a
    libpq-style DSN, not the `postgresql+psycopg://` SQLAlchemy dialect URL."""
    return database_url.replace("postgresql+psycopg://", "postgresql://")


async def init_checkpointer() -> AsyncPostgresSaver:
    global _saver_cm, _saver
    settings = get_settings()
    _saver_cm = AsyncPostgresSaver.from_conn_string(_psycopg_dsn(settings.DATABASE_URL))
    _saver = await _saver_cm.__aenter__()
    await _saver.setup()
    return _saver


async def close_checkpointer() -> None:
    global _saver_cm, _saver
    if _saver_cm is not None:
        await _saver_cm.__aexit__(None, None, None)
    _saver_cm = None
    _saver = None


def get_checkpointer() -> AsyncPostgresSaver:
    if _saver is None:
        raise RuntimeError("checkpointer not initialized — call init_checkpointer() during app startup")
    return _saver
