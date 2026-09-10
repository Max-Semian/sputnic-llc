"""File use-cases (application layer)."""

import logging
import mimetypes
import uuid
from collections.abc import AsyncIterator, Sequence
from pathlib import Path

from src.application.ports import FileStorage, UowFactory
from src.core.errors import AppError, FileNotFoundError, StoredFileMissingError
from src.domain.entities import StoredFile

logger = logging.getLogger(__name__)

MAX_NAME_LENGTH = 255


class FileService:
    """Create/list/rename/delete files; all DB access goes through the UoW."""

    def __init__(self, uow_factory: UowFactory, storage: FileStorage) -> None:
        self._uow_factory = uow_factory
        self._storage = storage

    async def list_files(self) -> Sequence[StoredFile]:
        async with self._uow_factory() as uow:
            return await uow.files.list_newest()

    async def get(self, file_id: str) -> StoredFile:
        async with self._uow_factory() as uow:
            item = await uow.files.get(file_id)
        if item is None:
            raise FileNotFoundError()
        return item

    async def get_download(self, file_id: str) -> tuple[StoredFile, Path]:
        item = await self.get(file_id)
        stored_path = self._storage.path(item.stored_name)
        if not stored_path.exists():
            raise StoredFileMissingError()
        return item, stored_path

    async def create(
        self,
        *,
        title: str,
        original_name: str,
        content_type: str | None,
        chunks: AsyncIterator[bytes],
    ) -> StoredFile:
        self._validate(title, field="title")
        self._validate(original_name or "unnamed", field="original_name")

        file_id = str(uuid.uuid4())
        suffix = Path(original_name or "").suffix
        stored_name = f"{file_id}{suffix}"

        # stream to disk (temp -> atomic rename)
        temp_path, size = await self._storage.write_temp(chunks)
        self._storage.commit(temp_path, stored_name)

        mime_type = content_type or mimetypes.guess_type(stored_name)[0]
        item = StoredFile(
            id=file_id,
            title=title,
            original_name=original_name or stored_name,
            stored_name=stored_name,
            mime_type=mime_type or "application/octet-stream",
            size=size,
        )

        try:
            async with self._uow_factory() as uow:
                await uow.files.add(item)
                await uow.commit()
                await uow.files.refresh(item)
        except BaseException:
            self._storage.delete(stored_name)
            raise
        return item

    async def update_title(self, file_id: str, title: str) -> StoredFile:
        self._validate(title, field="title")
        async with self._uow_factory() as uow:
            item = await uow.files.get(file_id)
            if item is None:
                raise FileNotFoundError()
            item.title = title
            await uow.commit()
            await uow.files.refresh(item)
        return item

    async def delete(self, file_id: str) -> None:
        async with self._uow_factory() as uow:
            item = await uow.files.get(file_id)
            if item is None:
                raise FileNotFoundError()
            stored_name = item.stored_name
            await uow.files.delete(item)
            await uow.commit()

        try:
            self._storage.delete(stored_name)
        except Exception:  # row is gone already; cleanup is best-effort
            logger.exception("Failed to remove stored file %s", stored_name)

    @staticmethod
    def _validate(value: str, *, field: str) -> None:
        if not value or len(value) > MAX_NAME_LENGTH:
            raise AppError(f"{field} must be between 1 and {MAX_NAME_LENGTH} characters")
