"""Application services: file & alert use-cases.

Functions are transport-agnostic (no FastAPI objects, no ``HTTPException``):
the API layer only maps arguments, and domain errors bubble up to be converted
into HTTP responses by the app's exception handlers.
"""

import logging
import mimetypes
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.errors import (
    FileNotFoundError,
    StoredFileMissingError,
)
from src.models import Alert, StoredFile
from src.storage import LocalStorage

logger = logging.getLogger(__name__)

MAX_ORIGINAL_NAME_LEN = 255


def _validate_name(value: str, *, field: str) -> None:
    if not value or len(value) > MAX_ORIGINAL_NAME_LEN:
        from src.errors import AppError

        raise AppError(f"{field} must be between 1 and {MAX_ORIGINAL_NAME_LEN} characters")


# ----------------------------------------------------------------------
# Reads
# ----------------------------------------------------------------------
async def list_files(session: AsyncSession) -> list[StoredFile]:
    result = await session.execute(
        select(StoredFile).order_by(StoredFile.created_at.desc())
    )
    return list(result.scalars().all())


async def list_alerts(session: AsyncSession) -> list[Alert]:
    result = await session.execute(select(Alert).order_by(Alert.created_at.desc()))
    return list(result.scalars().all())


async def get_file(session: AsyncSession, file_id: str) -> StoredFile:
    file_item = await session.get(StoredFile, file_id)
    if file_item is None:
        raise FileNotFoundError()
    return file_item


async def get_download(
    session: AsyncSession, storage: LocalStorage, file_id: str
) -> tuple[StoredFile, Path]:
    """Return ``(file_record, absolute_path)`` if the physical file exists."""
    file_item = await get_file(session, file_id)
    stored_path = storage.path(file_item.stored_name)
    if not stored_path.exists():
        raise StoredFileMissingError()
    return file_item, stored_path


# ----------------------------------------------------------------------
# Writes
# ----------------------------------------------------------------------
async def create_file(
    session: AsyncSession,
    storage: LocalStorage,
    *,
    title: str,
    original_name: str,
    content_type: str | None,
    chunks: AsyncIterator[bytes],
) -> StoredFile:
    """Stream an upload into storage and create its DB record atomically-ish.

    The previous version read the whole request body into memory
    (``upload_file.read()``), wrote it to disk, and only then inserted the row.
    Here the body is streamed chunk-by-chunk with a size cap; on any DB failure
    the just-written file is removed so no orphan files are left behind.
    """
    _validate_name(title, field="title")
    _validate_name(original_name or "unnamed", field="original_name")

    file_id = str(uuid.uuid4())
    suffix = Path(original_name or "").suffix
    stored_name = f"{file_id}{suffix}"

    # 1) stream to disk (temp -> atomic rename)
    temp_path, size = await storage.write_temp(chunks)
    storage.commit(temp_path, stored_name)

    mime_type = content_type or mimetypes.guess_type(stored_name)[0]
    file_item = StoredFile(
        id=file_id,
        title=title,
        original_name=original_name or stored_name,
        stored_name=stored_name,
        mime_type=mime_type or "application/octet-stream",
        size=size,
        processing_status="uploaded",
    )

    # 2) persist metadata; clean the file up if the DB write fails
    try:
        session.add(file_item)
        await session.commit()
        await session.refresh(file_item)
    except BaseException:
        storage.delete(stored_name)
        raise

    return file_item


async def update_file(session: AsyncSession, file_id: str, title: str) -> StoredFile:
    file_item = await get_file(session, file_id)
    file_item.title = title
    await session.commit()
    await session.refresh(file_item)
    return file_item


async def delete_file(
    session: AsyncSession, storage: LocalStorage, file_id: str
) -> None:
    """Delete a file row (alerts follow via ON DELETE CASCADE) and its content.

    Previously the physical file was removed *before* the row deletion, so a
    failed delete (e.g. FK violation caused by existing alerts) silently lost
    the stored bytes while keeping the DB record.
    """
    file_item = await get_file(session, file_id)
    stored_name = file_item.stored_name

    await session.delete(file_item)
    await session.commit()

    try:
        storage.delete(stored_name)
    except Exception:  # row is gone already; orphan cleanup is best-effort
        logger.exception("Failed to remove stored file %s", stored_name)
