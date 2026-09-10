"""SQLAlchemy repositories + Unit of Work (infrastructure layer).

This is the only place that knows SQLAlchemy query APIs; the application layer
depends on the protocols from ``src.application.ports``.
"""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.entities import Alert, StoredFile


class SqlAlchemyFileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, item: StoredFile) -> None:
        self._session.add(item)

    async def get(self, file_id: str) -> StoredFile | None:
        return await self._session.get(StoredFile, file_id)

    async def list_newest(self) -> Sequence[StoredFile]:
        result = await self._session.execute(
            select(StoredFile).order_by(StoredFile.created_at.desc())
        )
        return list(result.scalars().all())

    async def delete(self, item: StoredFile) -> None:
        await self._session.delete(item)

    async def refresh(self, item: StoredFile) -> None:
        await self._session.refresh(item)


class SqlAlchemyAlertRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, alert: Alert) -> None:
        self._session.add(alert)

    async def list_newest(self) -> Sequence[Alert]:
        result = await self._session.execute(select(Alert).order_by(Alert.created_at.desc()))
        return list(result.scalars().all())


class SqlAlchemyUnitOfWork:
    """Transaction boundary + repositories over one session."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory
        self.session: AsyncSession | None = None
        self.files: SqlAlchemyFileRepository | None = None
        self.alerts: SqlAlchemyAlertRepository | None = None

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        self.session = self._factory()
        self.files = SqlAlchemyFileRepository(self.session)
        self.alerts = SqlAlchemyAlertRepository(self.session)
        return self

    async def commit(self) -> None:
        assert self.session is not None
        await self.session.commit()

    async def rollback(self) -> None:
        assert self.session is not None
        await self.session.rollback()

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        assert self.session is not None
        if exc_type is not None:
            await self.session.rollback()
        await self.session.close()
