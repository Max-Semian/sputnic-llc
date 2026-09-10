"""Processing pipeline tests (application services + SQLite + temp storage).

These pin the original business statuses and alert semantics: clean files get
an info alert, suspicious files a warning, failed processing a critical one.
"""

import uuid
from pathlib import Path

import pytest_asyncio
from sqlalchemy import select

from src.application.services.processing_service import ProcessingService
from src.domain.entities import Alert, Base, StoredFile
from src.infrastructure.db import make_async_session_factory
from src.infrastructure.repositories import SqlAlchemyUnitOfWork
from src.infrastructure.storage import LocalStorage

MAX_SIZE = 10 * 1024 * 1024


@pytest_asyncio.fixture
async def env(tmp_path):
    """ProcessingService wired to a file-based SQLite DB and temp storage."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'db.sqlite'}"
    session_factory, engine = make_async_session_factory(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    storage = LocalStorage(tmp_path / "store", max_size=MAX_SIZE)
    service = ProcessingService(lambda: SqlAlchemyUnitOfWork(session_factory), storage)
    yield service, storage, session_factory
    await engine.dispose()


async def _seed(session_factory, storage, *, original_name, mime_type, content=None, stored=True):
    file_id = str(uuid.uuid4())
    stored_name = file_id + Path(original_name).suffix
    if stored and content is not None:
        (storage.root / stored_name).write_bytes(content)

    async with session_factory() as session:
        session.add(
            StoredFile(
                id=file_id,
                title="title",
                original_name=original_name,
                stored_name=stored_name,
                mime_type=mime_type,
                size=len(content) if content else 0,
            )
        )
        await session.commit()
    return file_id


async def _row(session_factory, file_id):
    async with session_factory() as session:
        row = await session.get(StoredFile, file_id)
        session.expunge(row)
        return row


async def _alerts(session_factory, file_id):
    async with session_factory() as session:
        result = await session.execute(select(Alert).where(Alert.file_id == file_id))
        alerts = list(result.scalars().all())
        for alert in alerts:
            session.expunge(alert)
        return alerts


async def test_clean_txt_goes_through_the_pipeline(env):
    service, storage, factory = env
    file_id = await _seed(
        factory, storage, original_name="report.txt", mime_type="text/plain",
        content=b"line1\nline2\n",
    )

    assert await service.scan(file_id) is True
    row = await _row(factory, file_id)
    assert row.processing_status == "processing"
    assert row.scan_status == "clean"
    assert row.scan_details == "no threats found"
    assert row.requires_attention is False

    assert await service.extract_metadata(file_id) is True
    row = await _row(factory, file_id)
    assert row.processing_status == "processed"
    assert row.metadata_json["line_count"] == 2
    assert row.metadata_json["char_count"] == 12

    assert await service.send_alert(file_id) is True
    alerts = await _alerts(factory, file_id)
    assert len(alerts) == 1
    assert alerts[0].level == "info"
    assert alerts[0].message == "File processed successfully"


async def test_suspicious_exe_gets_warning_alert(env):
    service, storage, factory = env
    file_id = await _seed(
        factory, storage, original_name="setup.exe", mime_type="application/octet-stream",
        content=b"MZ\x90\x00 executable-ish",
    )

    assert await service.scan(file_id) is True
    row = await _row(factory, file_id)
    assert row.scan_status == "suspicious"
    assert row.requires_attention is True
    assert "suspicious extension .exe" in row.scan_details

    assert await service.extract_metadata(file_id) is True
    assert await service.send_alert(file_id) is True

    alerts = await _alerts(factory, file_id)
    assert len(alerts) == 1
    assert alerts[0].level == "warning"
    assert "suspicious extension .exe" in alerts[0].message


async def test_fake_pdf_renamed_executable_is_flagged(env):
    service, storage, factory = env
    file_id = await _seed(
        factory, storage, original_name="invoice.pdf", mime_type="application/pdf",
        content=b"MZ\x90\x00 not really a pdf",
    )

    assert await service.scan(file_id) is True
    row = await _row(factory, file_id)
    assert row.scan_status == "suspicious"
    assert "pdf extension does not match file content" in row.scan_details


async def test_real_pdf_with_spoofed_mime_stays_clean(env):
    service, storage, factory = env
    file_id = await _seed(
        factory, storage, original_name="real.pdf", mime_type="text/plain",
        content=b"%PDF-1.7 fake minimal pdf",
    )

    assert await service.scan(file_id) is True
    row = await _row(factory, file_id)
    assert row.scan_status == "clean"
    assert row.requires_attention is False


async def test_missing_file_phases_return_false(env):
    service, storage, factory = env
    await _seed(factory, storage, original_name="a.txt", mime_type="text/plain", content=b"x")
    assert await service.scan("no-such-file") is False
    assert await service.extract_metadata("no-such-file") is False
    assert await service.send_alert("no-such-file") is False


async def test_missing_stored_bytes_marks_failed_and_critical_alert(env):
    service, storage, factory = env
    file_id = await _seed(
        factory, storage, original_name="gone.txt", mime_type="text/plain",
        content=b"x", stored=False,
    )

    assert await service.extract_metadata(file_id) is True
    row = await _row(factory, file_id)
    assert row.processing_status == "failed"
    assert row.scan_details == "stored file not found during metadata extraction"

    assert await service.send_alert(file_id) is True
    alerts = await _alerts(factory, file_id)
    assert len(alerts) == 1
    assert alerts[0].level == "critical"
    assert alerts[0].message == "File processing failed"


async def test_run_all_runs_inline_pipeline(env):
    """Broker-down fallback produces the same end state as the task chain."""
    service, storage, factory = env
    file_id = await _seed(
        factory, storage, original_name="doc.txt", mime_type="text/plain", content=b"hello\n"
    )

    await service.run_all(file_id)

    row = await _row(factory, file_id)
    assert row.processing_status == "processed"
    assert row.scan_status == "clean"
    assert row.metadata_json["char_count"] == 6
    alerts = await _alerts(factory, file_id)
    assert len(alerts) == 1
    assert alerts[0].level == "info"
