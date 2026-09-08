"""Worker pipeline tests.

Phase functions are executed against a patched sync SQLite engine and a
temporary storage root, so no Celery broker / Postgres is required. These tests
pin the original business statuses and alert semantics.
"""

import uuid
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.worker import tasks as wt
from src.models import Alert, Base, StoredFile
from src.storage import LocalStorage


def _uid() -> str:
    return str(uuid.uuid4())


def _seed(tmp_path, monkeypatch, *, original_name, mime_type, content=None, stored=True):
    """Insert a file row + optional stored bytes; patch worker DB/storage."""
    engine = create_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    Base.metadata.create_all(engine)

    store_root = tmp_path / "store"
    local = LocalStorage(store_root, max_size=10 * 1024 * 1024)
    monkeypatch.setattr(wt, "_sync_engine", engine)
    monkeypatch.setattr(wt, "storage", local)

    file_id = _uid()
    stored_name = file_id + Path(original_name).suffix
    if stored and content is not None:
        (store_root / stored_name).write_bytes(content)

    with sessionmaker(bind=engine)() as session:
        session.add(
            StoredFile(
                id=file_id,
                title="title",
                original_name=original_name,
                stored_name=stored_name,
                mime_type=mime_type,
                size=len(content) if content else 0,
                processing_status="uploaded",
            )
        )
        session.commit()
    return file_id


def _row(file_id):
    with wt._session() as session:
        row = session.get(StoredFile, file_id)
        session.expunge(row)
        return row


def _alerts(file_id):
    from sqlalchemy import select

    with wt._session() as session:
        result = session.execute(select(Alert).where(Alert.file_id == file_id))
        alerts = list(result.scalars().all())
        for a in alerts:
            session.expunge(a)
        return alerts


def test_clean_txt_goes_through_the_pipeline(tmp_path, monkeypatch):
    file_id = _seed(
        tmp_path, monkeypatch,
        original_name="report.txt",
        mime_type="text/plain",
        content=b"line1\nline2\n",
    )

    assert wt.scan_file_phase(file_id) is True
    row = _row(file_id)
    assert row.processing_status == "processing"
    assert row.scan_status == "clean"
    assert row.scan_details == "no threats found"
    assert row.requires_attention is False

    assert wt.extract_metadata_phase(file_id) is True
    row = _row(file_id)
    assert row.processing_status == "processed"
    assert row.metadata_json["line_count"] == 2
    assert row.metadata_json["char_count"] == 12

    assert wt.send_alert_phase(file_id) is True
    alerts = _alerts(file_id)
    assert len(alerts) == 1
    assert alerts[0].level == "info"
    assert alerts[0].message == "File processed successfully"


def test_suspicious_exe_gets_warning_alert(tmp_path, monkeypatch):
    file_id = _seed(
        tmp_path, monkeypatch,
        original_name="setup.exe",
        mime_type="application/octet-stream",
        content=b"MZ\x90\x00 executable-ish",
    )

    assert wt.scan_file_phase(file_id) is True
    row = _row(file_id)
    assert row.scan_status == "suspicious"
    assert row.requires_attention is True
    assert "suspicious extension .exe" in row.scan_details

    assert wt.extract_metadata_phase(file_id) is True
    assert wt.send_alert_phase(file_id) is True

def test_fake_pdf_renamed_executable_is_flagged(tmp_path, monkeypatch):
    """Client lies about the MIME type; content sniffing catches the rename."""
    file_id = _seed(
        tmp_path, monkeypatch,
        original_name="invoice.pdf",
        mime_type="application/pdf",
        content=b"MZ\x90\x00 not really a pdf",
    )

    assert wt.scan_file_phase(file_id) is True
    row = _row(file_id)
    assert row.scan_status == "suspicious"
    assert "pdf extension does not match file content" in row.scan_details


def test_real_pdf_with_spoofed_mime_stays_clean(tmp_path, monkeypatch):
    file_id = _seed(
        tmp_path, monkeypatch,
        original_name="real.pdf",
        mime_type="text/plain",  # spoofed by the uploader
        content=b"%PDF-1.7 fake minimal pdf",
    )

    assert wt.scan_file_phase(file_id) is True
    row = _row(file_id)
    assert row.scan_status == "clean"
    assert row.requires_attention is False


def test_missing_file_phases_return_false(tmp_path, monkeypatch):
    _seed(
        tmp_path, monkeypatch,
        original_name="a.txt", mime_type="text/plain", content=b"x",
    )
    assert wt.scan_file_phase("no-such-file") is False
    assert wt.extract_metadata_phase("no-such-file") is False
    assert wt.send_alert_phase("no-such-file") is False


def test_missing_stored_bytes_marks_failed_and_critical_alert(tmp_path, monkeypatch):
    file_id = _seed(
        tmp_path, monkeypatch,
        original_name="gone.txt",
        mime_type="text/plain",
        content=b"x",
        stored=False,  # row exists but bytes are missing
    )

    assert wt.extract_metadata_phase(file_id) is True
    row = _row(file_id)
    assert row.processing_status == "failed"
    assert row.scan_details == "stored file not found during metadata extraction"

    assert wt.send_alert_phase(file_id) is True
    alerts = _alerts(file_id)
    assert len(alerts) == 1
    assert alerts[0].level == "critical"
    assert alerts[0].message == "File processing failed"


def test_process_file_fully_runs_inline_pipeline(tmp_path, monkeypatch):
    """Broker-down fallback produces the same end state as the task chain."""
    file_id = _seed(
        tmp_path, monkeypatch,
        original_name="doc.txt",
        mime_type="text/plain",
        content=b"hello\n",
    )

    wt.process_file_fully(file_id)

    row = _row(file_id)
    assert row.processing_status == "processed"
    assert row.scan_status == "clean"
    assert row.metadata_json["char_count"] == 6
    alerts = _alerts(file_id)
    assert len(alerts) == 1
    assert alerts[0].level == "info"

