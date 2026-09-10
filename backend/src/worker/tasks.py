"""Celery tasks (worker layer).

Thin wrappers: each task builds the same ``ProcessingService`` used by the API
(per-run async engine with NullPool, disposed afterwards) and executes one
pipeline phase. No event-loop hack, no duplicated data access.

Pipeline (unchanged business flow):
    upload -> scan -> extract metadata -> send alert
"""

import asyncio
import logging
import threading
from collections.abc import Callable, Coroutine
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker

from src.application.services.processing_service import ProcessingService
from src.core.config import get_settings
from src.infrastructure.celery_app import celery_app
from src.infrastructure.db import make_async_engine
from src.infrastructure.repositories import SqlAlchemyUnitOfWork
from src.infrastructure.storage import LocalStorage

logger = logging.getLogger(__name__)

settings = get_settings()
storage = LocalStorage(
    settings.storage_dir,
    max_size=settings.max_upload_size,
    chunk_size=settings.chunk_size,
)


async def _with_service(callback: Callable[[ProcessingService], Coroutine[Any, Any, Any]]) -> Any:
    engine = make_async_engine(settings.async_database_url, null_pool=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    service = ProcessingService(lambda: SqlAlchemyUnitOfWork(session_factory), storage)
    try:
        return await callback(service)
    finally:
        await engine.dispose()


def _run(callback: Callable[[ProcessingService], Coroutine[Any, Any, Any]]) -> Any:
    return asyncio.run(_with_service(callback))


def _mark_failed(file_id: str, details: str) -> None:
    try:
        _run(lambda service: service.mark_failed(file_id, details))
    except Exception:  # pragma: no cover - failure handling must not raise
        logger.exception("Could not mark file %s as failed", file_id)


@celery_app.task(name="src.worker.tasks.scan_file_for_threats")
def scan_file_for_threats(file_id: str) -> None:
    try:
        exists = _run(lambda service: service.scan(file_id))
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
        exists = _run(lambda service: service.extract_metadata(file_id))
    except Exception:
        logger.exception("Metadata extraction failed for %s", file_id)
        _mark_failed(file_id, "metadata extraction failed")
        send_file_alert.delay(file_id)
        raise
    if exists:
        send_file_alert.delay(file_id)


@celery_app.task(name="src.worker.tasks.send_file_alert")
def send_file_alert(file_id: str) -> None:
    _run(lambda service: service.send_alert(file_id))


def process_file_fully(file_id: str) -> None:
    """Run the whole pipeline synchronously (fallback when the broker is down)."""
    try:
        _run(lambda service: service.run_all(file_id))
    except Exception:
        logger.exception("Inline processing failed for %s", file_id)
        _mark_failed(file_id, "processing failed")


def enqueue_scan(file_id: str) -> None:
    """Schedule the scan via Celery; fall back to inline processing if needed."""
    try:
        scan_file_for_threats.delay(file_id)
    except Exception:
        logger.exception("Broker unavailable; processing file %s inline", file_id)
        threading.Thread(target=process_file_fully, args=(file_id,), daemon=True).start()
