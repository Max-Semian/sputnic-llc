"""Background processing pipeline (Celery worker).

The original worker ran async SQLAlchemy behind a hand-rolled
``asyncio.new_event_loop`` bridge and imported the FastAPI-typed service module,
creating *two* engines inside one process. Here the worker owns a single lazy
sync engine (psycopg), phases are plain synchronous functions, and the only
module shared with the API is this one (importing it has no side effects).

Pipeline (identical to the previous business flow):
    upload -> scan (threat rules) -> extract metadata -> send alert
"""

import logging
import threading
from pathlib import Path

from celery import Celery
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.config import get_settings
from src.models import Alert, StoredFile
from src.scanner import evaluate_threats, extract_pdf_metadata, extract_text_metadata
from src.storage import LocalStorage

logger = logging.getLogger(__name__)

PROCESSING_STATUS_UPLOADED = "uploaded"
PROCESSING_STATUS_PROCESSING = "processing"
PROCESSING_STATUS_PROCESSED = "processed"
PROCESSING_STATUS_FAILED = "failed"

SCAN_CLEAN = "clean"
SCAN_SUSPICIOUS = "suspicious"

_HEADER_BYTES = 4096
_MESSAGE_LIMIT = 500

settings = get_settings()
storage = LocalStorage(
    settings.storage_dir,
    max_size=settings.max_upload_size,
    chunk_size=settings.chunk_size,
)

celery_app = Celery(
    "sputnik.tasks",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

_sync_engine = None
_engine_lock = threading.Lock()


def _get_sync_engine():
    """Lazily create the worker's sync engine (per worker process)."""
    global _sync_engine
    with _engine_lock:
        if _sync_engine is None:
            _sync_engine = create_engine(settings.sync_database_url, pool_pre_ping=True)
    return _sync_engine


def _session() -> Session:
    return sessionmaker(bind=_get_sync_engine(), expire_on_commit=False)()


# ----------------------------------------------------------------------
# Phase helpers
# ----------------------------------------------------------------------
def _header_bytes(path: Path) -> bytes:
    try:
        with path.open("rb") as fh:
            return fh.read(_HEADER_BYTES)
    except FileNotFoundError:
        return b""


def scan_file_phase(file_id: str) -> bool:
    """Apply threat rules. Returns False when the file no longer exists."""
    with _session() as session:
        item = session.get(StoredFile, file_id)
        if item is None:
            return False

        extension = Path(item.original_name).suffix.lower()
        header = _header_bytes(storage.path(item.stored_name))
        reasons = evaluate_threats(
            extension=extension,
            size=item.size,
            header=header,
        )

        item.processing_status = PROCESSING_STATUS_PROCESSING
        item.scan_status = SCAN_SUSPICIOUS if reasons else SCAN_CLEAN
        item.scan_details = ", ".join(reasons) if reasons else "no threats found"
        item.requires_attention = bool(reasons)
        session.commit()
    return True


def extract_metadata_phase(file_id: str) -> bool:
    """Extract lightweight metadata; marks the file processed. False = gone."""
    with _session() as session:
        item = session.get(StoredFile, file_id)
        if item is None:
            return False

        stored_path = storage.path(item.stored_name)
        if not stored_path.exists():
            item.processing_status = PROCESSING_STATUS_FAILED
            item.scan_status = item.scan_status or PROCESSING_STATUS_FAILED
            item.scan_details = "stored file not found during metadata extraction"
            session.commit()
            return True

        metadata = {
            "extension": Path(item.original_name).suffix.lower(),
            "size_bytes": item.size,
            "mime_type": item.mime_type,
        }
        mime_type = item.mime_type or ""
        if mime_type.startswith("text/"):
            metadata.update(extract_text_metadata(stored_path))
        elif mime_type == "application/pdf":
            metadata.update(extract_pdf_metadata(stored_path))

        item.metadata_json = metadata
        item.processing_status = PROCESSING_STATUS_PROCESSED
        session.commit()
    return True


def send_alert_phase(file_id: str) -> bool:
    """Create the alert for a finished pipeline. False = file already gone."""
    with _session() as session:
        item = session.get(StoredFile, file_id)
        if item is None:
            return False

        if item.processing_status == PROCESSING_STATUS_FAILED:
            level, message = "critical", "File processing failed"
        elif item.requires_attention:
            level, message = "warning", f"File requires attention: {item.scan_details}"
        else:
            level, message = "info", "File processed successfully"

        session.add(
            Alert(
                file_id=file_id,
                level=level,
                message=message[:_MESSAGE_LIMIT],
            )
        )
        session.commit()
    return True


def _mark_failed(file_id: str, details: str) -> None:
    """Best-effort transition to ``failed`` after an unexpected error."""
    try:
        with _session() as session:
            item = session.get(StoredFile, file_id)
            if item is None:
                return
            item.processing_status = PROCESSING_STATUS_FAILED
            item.scan_status = item.scan_status or PROCESSING_STATUS_FAILED
            item.scan_details = details[:_MESSAGE_LIMIT]
            session.commit()
    except Exception:  # pragma: no cover - failure handling must not raise
        logger.exception("Could not mark file %s as failed", file_id)


# ----------------------------------------------------------------------
# Celery tasks
# ----------------------------------------------------------------------
@celery_app.task(name="src.worker.tasks.scan_file_for_threats")
def scan_file_for_threats(file_id: str) -> None:
    try:
        exists = scan_file_phase(file_id)
    except Exception:
        logger.exception("Threat scan failed for %s", file_id)
        _mark_failed(file_id, "threat scan failed")
        send_file_alert.delay(file_id)
        raise
    if exists:
        extract_file_metadata.delay(file_id)


@celery_app.task(name="src.worker.tasks.extract_file_metadata")
def extract_file_metadata(file_id: str) -> None:
    try:
        exists = extract_metadata_phase(file_id)
    except Exception:
        logger.exception("Metadata extraction failed for %s", file_id)
        _mark_failed(file_id, "metadata extraction failed")
        send_file_alert.delay(file_id)
        raise
    if exists:
        send_file_alert.delay(file_id)


@celery_app.task(name="src.worker.tasks.send_file_alert")
def send_file_alert(file_id: str) -> None:
    send_alert_phase(file_id)


def process_file_fully(file_id: str) -> None:
    """Run the whole pipeline synchronously (fallback when the broker is down)."""
    try:
        if scan_file_phase(file_id):
            if extract_metadata_phase(file_id):
                send_alert_phase(file_id)
    except Exception:
        logger.exception("Inline processing failed for %s", file_id)
        _mark_failed(file_id, "processing failed")


def enqueue_scan(file_id: str) -> None:
    """Schedule the scan via Celery; fall back to inline processing if needed.

    The old code called ``.delay()`` directly from the endpoint, so a broker
    outage turned a successful upload into an HTTP 500 with the file already
    stored. Here the endpoint never fails because of the queue: the pipeline is
    run in a background thread instead.
    """
    try:
        scan_file_for_threats.delay(file_id)
    except Exception:
        logger.exception("Broker unavailable; processing file %s inline", file_id)
        threading.Thread(target=process_file_fully, args=(file_id,), daemon=True).start()


