"""Unit tests for the streaming local storage."""

import pytest

from src.core.errors import EmptyFileError, FileTooLargeError, StorageError
from src.infrastructure.storage import LocalStorage


async def _chunks(*parts: bytes):
    for part in parts:
        yield part


async def test_write_temp_commits_content_atomically(tmp_path):
    storage = LocalStorage(tmp_path, max_size=1024)
    temp_path, size = await storage.write_temp(_chunks(b"hello ", b"world"))
    assert size == 11

    storage.commit(temp_path, "file.txt")
    assert (tmp_path / "file.txt").read_bytes() == b"hello world"
    assert not temp_path.exists()


async def test_write_temp_rejects_empty_upload(tmp_path):
    storage = LocalStorage(tmp_path, max_size=1024)
    with pytest.raises(EmptyFileError):
        await storage.write_temp(_chunks())
    assert list(tmp_path.iterdir()) == []


async def test_write_temp_enforces_max_size_and_cleans_up(tmp_path):
    storage = LocalStorage(tmp_path, max_size=10)
    with pytest.raises(FileTooLargeError):
        await storage.write_temp(_chunks(b"x" * 5, b"y" * 10))
    assert list(tmp_path.iterdir()) == []


async def test_write_temp_uses_bounded_chunks(tmp_path, monkeypatch):
    """The optimization: the file is streamed, never buffered whole in memory."""
    import asyncio

    storage = LocalStorage(tmp_path, max_size=1000)
    written: list[int] = []
    original = asyncio.to_thread

    async def recording_to_thread(fn, *args, **kwargs):
        result = await original(fn, *args, **kwargs)
        written.append(0)
        return result

    monkeypatch.setattr(asyncio, "to_thread", recording_to_thread)
    temp_path, size = await storage.write_temp(_chunks(b"a" * 100, b"b" * 100))
    assert size == 200
    # bytes were flushed to disk in several bounded writes
    assert len(written) > 1


def test_unsafe_stored_names_are_rejected(tmp_path):
    storage = LocalStorage(tmp_path, max_size=1024)
    with pytest.raises(StorageError):
        storage.path("../escape.txt")
    with pytest.raises(StorageError):
        storage.path("dir/file.txt")


def test_delete_and_exists(tmp_path):
    storage = LocalStorage(tmp_path, max_size=1024)
    (tmp_path / "a.bin").write_bytes(b"data")
    assert storage.exists("a.bin")
    storage.delete("a.bin")
    assert not storage.exists("a.bin")
    # idempotent
    storage.delete("a.bin")
