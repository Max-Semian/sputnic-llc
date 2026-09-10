"""Database engine/session helpers (infrastructure layer).

No engine is created at import time: the app and the worker each build their
own engine via these factories.
"""

from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool, StaticPool


def _enable_sqlite_fk(engine: AsyncEngine) -> None:
    """SQLite disables FK enforcement by default; tests need ON DELETE CASCADE."""

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def make_async_engine(
    url: str, *, static_pool: bool = False, null_pool: bool = False
) -> AsyncEngine:
    """Create an async engine.

    ``static_pool`` is required for in-memory SQLite (one shared connection);
    ``null_pool`` is used by short-lived worker runs (one connection per task,
    disposed with the engine).
    """
    kwargs: dict = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    if null_pool:
        kwargs["poolclass"] = NullPool
    elif static_pool or url.startswith("sqlite+aiosqlite:///:memory:"):
        kwargs["poolclass"] = StaticPool

    engine = create_async_engine(url, pool_pre_ping=not url.startswith("sqlite"), **kwargs)
    if url.startswith("sqlite"):
        _enable_sqlite_fk(engine)
    return engine


def make_async_session_factory(
    url: str, *, static_pool: bool = False, null_pool: bool = False
) -> tuple[async_sessionmaker[AsyncSession], AsyncEngine]:
    engine = make_async_engine(url, static_pool=static_pool, null_pool=null_pool)
    return async_sessionmaker(engine, expire_on_commit=False), engine


async def session_scope(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    """Yield a session, committing on success and rolling back on error."""
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
