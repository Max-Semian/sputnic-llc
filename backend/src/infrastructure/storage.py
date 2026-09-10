"""Local filesystem storage (infrastructure layer).

Streams writes in bounded chunks and commits atomically (temp file +
``os.replace``); implements the ``FileStorage`` protocol from the application
layer, so an S3-backed implementation can replace it without touching services.
"""

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from src.core.errors import EmptyFileError, FileTooLargeError, StorageError

logger = logging.getLogger(__name__)


class LocalStorage:
    def __init__(self, root: Path, *, max_size: int, chunk_size: int = 1024 * 1024) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_size = max_size
        self.chunk_size = chunk_size

    # --- path safety ---------------------------------------------------
    def _resolve(self, stored_name: str) -> Path:
        if not stored_name or stored_name != Path(stored_name).name:
            raise StorageError(f"Unsafe stored name: {stored_name!r}")
        return self.root / stored_name

    def path(self, stored_name: str) -> Path:
        return self._resolve(stored_name)

    def exists(self, stored_name: str) -> bool:
        return self.path(stored_name).exists()

    def delete(self, stored_name: str) -> None:
        path = self._resolve(stored_name)
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:  # pragma: no cover - fs edge case
            raise StorageError(f"Could not delete stored file: {exc}") from exc

    def open_binary(self, stored_name: str):
        return self.path(stored_name).open("rb")

    def read(self, stored_name: str) -> bytes:
        return self.path(stored_name).read_bytes()

    # --- atomic streaming writes ---------------------------------------
    async def write_temp(self, chunks: AsyncIterator[bytes]) -> tuple[Path, int]:
        """Stream ``chunks`` to a temp file; return ``(temp_path, size)``.

        Raises EmptyFileError/FileTooLargeError before the caller commits
        anything; nothing is left behind on failure.
        """
        tmp_path = self.root / f".upload-{uuid.uuid4().hex}.part"
        size = 0
        try:
            with tmp_path.open("wb") as fh:
                async for chunk in chunks:
                    if not chunk:
                        continue
                    size += len(chunk)
                    if size > self.max_size:
                        raise FileTooLargeError(
                            f"File exceeds the maximum allowed size of {self.max_size} bytes"
                        )
                    await asyncio.to_thread(fh.write, chunk)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise

        if size == 0:
            tmp_path.unlink(missing_ok=True)
            raise EmptyFileError()
        return tmp_path, size

    def commit(self, temp_path: Path, stored_name: str) -> Path:
        final = self._resolve(stored_name)
        try:
            temp_path.replace(final)
        except OSError as exc:  # pragma: no cover - fs edge case
            raise StorageError(f"Could not commit stored file: {exc}") from exc
        return final

    def discard(self, temp_path: Path) -> None:
        temp_path.unlink(missing_ok=True)
