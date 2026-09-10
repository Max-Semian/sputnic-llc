"""Repository / Unit of Work tests: CRUD, ordering and ON DELETE CASCADE."""

from datetime import datetime, timedelta, timezone

import pytest_asyncio
from sqlalchemy import func, select

from src.domain.entities import Alert, Base, StoredFile
from src.infrastructure.db import make_async_session_factory
from src.infrastructure.repositories import SqlAlchemyUnitOfWork


@pytest_asyncio.fixture
async def session_factory(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'repos.sqlite'}"
    factory, engine = make_async_session_factory(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield factory
    await engine.dispose()


def _file(file_id: str, *, created_at: datetime) -> StoredFile:
    return StoredFile(
        id=file_id,
        title="title",
        original_name=f"{file_id}.txt",
        stored_name=f"{file_id}.txt",
        mime_type="text/plain",
        size=1,
        processing_status="uploaded",
        created_at=created_at,
        updated_at=created_at,
    )


async def test_file_repository_add_get_list_and_delete(session_factory):
    now = datetime.now(timezone.utc)
    uow = SqlAlchemyUnitOfWork(session_factory)

    async with uow:
        await uow.files.add(_file("older-file", created_at=now - timedelta(hours=2)))
        await uow.files.add(_file("newer-file", created_at=now - timedelta(hours=1)))
        await uow.commit()

    async with uow:
        got = await uow.files.get("older-file")
        assert got is not None
        assert got.title == "title"
        assert isinstance(got, StoredFile)

        items = await uow.files.list_newest()
        assert [item.id for item in items] == ["newer-file", "older-file"]

    async with uow:
        item = await uow.files.get("older-file")
        await uow.files.delete(item)
        await uow.commit()

    async with uow:
        assert await uow.files.get("older-file") is None
        assert await uow.files.get("newer-file") is not None


async def test_alert_repository_lists_newest_first(session_factory):
    now = datetime.now(timezone.utc)
    uow = SqlAlchemyUnitOfWork(session_factory)

    async with uow:
        await uow.files.add(_file("f", created_at=now))
        await uow.commit()

    async with uow:
        await uow.alerts.add(Alert(file_id="f", level="info", message="old", created_at=now - timedelta(minutes=5)))
        await uow.alerts.add(Alert(file_id="f", level="warning", message="new", created_at=now))
        await uow.commit()

    async with uow:
        alerts = await uow.alerts.list_newest()
        assert [a.message for a in alerts] == ["new", "old"]


async def test_delete_file_cascades_alerts(session_factory):
    """ON DELETE CASCADE: deleting a file removes its alerts (regression)."""
    now = datetime.now(timezone.utc)
    uow = SqlAlchemyUnitOfWork(session_factory)

    async with uow:
        await uow.files.add(_file("cascade-file", created_at=now))
        await uow.commit()
    async with uow:
        await uow.alerts.add(Alert(file_id="cascade-file", level="info", message="m"))
        await uow.commit()

    async with uow:
        item = await uow.files.get("cascade-file")
        await uow.files.delete(item)
        await uow.commit()

    async with session_factory() as session:
        count = await session.scalar(
            select(func.count()).select_from(Alert).where(Alert.file_id == "cascade-file")
        )
    assert count == 0
