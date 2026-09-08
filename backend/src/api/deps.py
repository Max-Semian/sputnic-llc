"""FastAPI dependencies (delivery-layer wiring)."""

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage import LocalStorage


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Provide a DB session from the app-level engine (see ``src.main``)."""
    factory = request.app.state.session_factory
    async with factory() as session:
        try:
            yield session
        except BaseException:
            await session.rollback()
            raise


def get_storage(request: Request) -> LocalStorage:
    return request.app.state.storage
