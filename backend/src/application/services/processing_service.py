"""Asynchronous file-processing pipeline (application layer).

Same business flow as before: scan -> extract metadata -> send alert.
All DB access goes through the Unit of Work; scanning rules/counters come from
``src.domain.scanning``. File reads are pushed to a thread so the event loop is
not blocked (relevant for the inline fallback inside the API process).
"""

import asyncio
import logging
from pathlib import Path

from src.application.ports import FileStorage, UowFactory
from src.core.enums import AlertLevel, ProcessingStatus, ScanStatus
from src.domain.entities import Alert, StoredFile
from src.domain.scanning import (
    evaluate_threats,
    extract_pdf_metadata,
    extract_text_metadata,
    read_header,
)

logger = logging.getLogger(__name__)

MESSAGE_LIMIT = 500


class ProcessingService:
    def __init__(self, uow_factory: UowFactory, storage: FileStorage) -> None:
        self._uow_factory = uow_factory
        self._storage = storage

    async def scan(self, file_id: str) -> bool:
        """Apply threat rules. Returns False when the file no longer exists."""
        async with self._uow_factory() as uow:
            item = await uow.files.get(file_id)
            if item is None:
                return False

            extension = Path(item.original_name).suffix.lower()
            header = await asyncio.to_thread(read_header, self._storage.path(item.stored_name))
            reasons = evaluate_threats(extension=extension, size=item.size, header=header)

            item.processing_status = ProcessingStatus.PROCESSING
            item.scan_status = ScanStatus.SUSPICIOUS if reasons else ScanStatus.CLEAN
            item.scan_details = ", ".join(reasons) if reasons else "no threats found"
            item.requires_attention = bool(reasons)
            await uow.commit()
        return True

    async def extract_metadata(self, file_id: str) -> bool:
        """Extract lightweight metadata; marks the file processed. False = gone."""
        async with self._uow_factory() as uow:
            item = await uow.files.get(file_id)
            if item is None:
                return False

            stored_path = self._storage.path(item.stored_name)
            if not await asyncio.to_thread(stored_path.exists):
                item.processing_status = ProcessingStatus.FAILED
                item.scan_status = item.scan_status or ScanStatus.FAILED
                item.scan_details = "stored file not found during metadata extraction"
                await uow.commit()
                return True

            metadata = {
                "extension": Path(item.original_name).suffix.lower(),
                "size_bytes": item.size,
                "mime_type": item.mime_type,
            }
            mime_type = item.mime_type or ""
            if mime_type.startswith("text/"):
                metadata.update(await asyncio.to_thread(extract_text_metadata, stored_path))
            elif mime_type == "application/pdf":
                metadata.update(await asyncio.to_thread(extract_pdf_metadata, stored_path))

            item.metadata_json = metadata
            item.processing_status = ProcessingStatus.PROCESSED
            await uow.commit()
        return True

    async def send_alert(self, file_id: str) -> bool:
        """Create the alert for a finished pipeline. False = file already gone."""
        async with self._uow_factory() as uow:
            item = await uow.files.get(file_id)
            if item is None:
                return False

            if item.processing_status == ProcessingStatus.FAILED:
                level, message = AlertLevel.CRITICAL, "File processing failed"
            elif item.requires_attention:
                level, message = AlertLevel.WARNING, f"File requires attention: {item.scan_details}"
            else:
                level, message = AlertLevel.INFO, "File processed successfully"

            await uow.alerts.add(
                Alert(file_id=file_id, level=level, message=message[:MESSAGE_LIMIT])
            )
            await uow.commit()
        return True

    async def mark_failed(self, file_id: str, details: str) -> None:
        """Best-effort transition to ``failed`` after an unexpected error."""
        async with self._uow_factory() as uow:
            item: StoredFile | None = await uow.files.get(file_id)
            if item is None:
                return
            item.processing_status = ProcessingStatus.FAILED
            item.scan_status = item.scan_status or ScanStatus.FAILED
            item.scan_details = details[:MESSAGE_LIMIT]
            await uow.commit()

    async def run_all(self, file_id: str) -> None:
        """Run the whole pipeline in one pass (broker-down fallback)."""
        if await self.scan(file_id):
            if await self.extract_metadata(file_id):
                await self.send_alert(file_id)
