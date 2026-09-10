"""Shared pytest fixtures.

The whole backend is tested against an in-memory SQLite database
(``aiosqlite`` + ``StaticPool``), so the suite needs no external services.
"""

import httpx
import pytest_asyncio
from asgi_lifespan import LifespanManager

from src.core.config import Settings
from src.domain.entities import Base
from src.infrastructure.db import make_async_session_factory

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def session_factory():
    """Async session factory with schema created on an in-memory SQLite DB."""
    factory, engine = make_async_session_factory(TEST_DB_URL, static_pool=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch):
    """FastAPI app (fresh in-memory DB + temp storage) wrapped in AsyncClient.

    ``enqueue_scan`` is stubbed: the broker is not available in unit tests and
    scheduling is verified by inspecting recorded file ids.
    """
    from src.presentation import routes as api_routes
    from src.presentation.app import create_app

    settings = Settings(
        database_url=TEST_DB_URL,
        storage_dir=tmp_path / "storage",
        max_upload_size=1_000_000,
        chunk_size=64 * 1024,
    )
    enqueued: list[str] = []
    monkeypatch.setattr(api_routes, "enqueue_scan", lambda file_id: enqueued.append(file_id))

    app = create_app(settings)
    async with LifespanManager(app):
        async with app.state.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            c.enqueued = enqueued  # type: ignore[attr-defined]
            c.app = app  # type: ignore[attr-defined]
            yield c
