"""Database engine / session helpers.

Engines are created explicitly from a settings instance so that FastAPI
(``create_app``) and the Celery worker each own the engine they need. No engine
is created at import time anymore.
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def _enable_sqlite_fk(engine: AsyncEngine) -> None:
    from sqlalchemy import event

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def make_async_engine(url: str, *, static_pool: bool = False) -> AsyncEngine:
    """Create an async engine for ``url``.

    ``static_pool`` must be used for in-memory SQLite (one shared connection).
    """
    kwargs: dict = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    if url.startswith("sqlite+aiosqlite:///:memory:") or static_pool:
        kwargs["poolclass"] = StaticPool

    engine = create_async_engine(url, pool_pre_ping=not url.startswith("sqlite"), **kwargs)
    if url.startswith("sqlite"):
        _enable_sqlite_fk(engine)
    return engine


def make_async_session_factory(url: str, *, static_pool: bool = False) -> tuple[async_sessionmaker[AsyncSession], AsyncEngine]:
    """Return an ``(async_sessionmaker, engine)`` pair for ``url``."""
    engine = make_async_engine(url, static_pool=static_pool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return factory, engine


def make_sync_session_factory(url: str) -> sessionmaker[Session]:
    """Create a sync session factory (used by the Celery worker)."""
    engine_kwargs: dict = {}
    if url.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    from sqlalchemy import create_engine

    engine = create_engine(url, pool_pre_ping=not url.startswith("sqlite"), **engine_kwargs)
    if url.startswith("sqlite"):
        from sqlalchemy import event

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):  # noqa: ANN001
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return sessionmaker(bind=engine, expire_on_commit=False)


async def session_scope(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    """Yield a session and guarantee rollback/close on error."""
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
