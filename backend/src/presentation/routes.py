"""HTTP endpoints (presentation layer).

Thin layer: parse input, call application services, return DTOs. Domain errors
are mapped to HTTP responses by the app-level exception handler.
"""

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse

from src.application.services.alert_service import AlertService
from src.application.services.file_service import FileService
from src.presentation.deps import get_alert_service, get_file_service
from src.presentation.schemas import AlertItem, FileItem, FileUpdate
from src.worker.tasks import enqueue_scan

router = APIRouter()

_UPLOAD_CHUNK = 1024 * 1024


async def _upload_chunks(
    upload: UploadFile, chunk_size: int = _UPLOAD_CHUNK
) -> AsyncIterator[bytes]:
    """Read an UploadFile in bounded chunks instead of loading it fully."""
    while True:
        chunk = await upload.read(chunk_size)
        if not chunk:
            break
        yield chunk


@router.get("/files", response_model=list[FileItem])
async def list_files_view(file_service: FileService = Depends(get_file_service)):
    return await file_service.list_files()


@router.get("/alerts", response_model=list[AlertItem])
async def list_alerts_view(alert_service: AlertService = Depends(get_alert_service)):
    return await alert_service.list_alerts()


@router.post("/files", response_model=FileItem, status_code=201)
async def create_file_view(
    title: str = Form(...),
    file: UploadFile = File(...),
    file_service: FileService = Depends(get_file_service),
):
    file_item = await file_service.create(
        title=title,
        original_name=file.filename or "",
        content_type=file.content_type,
        chunks=_upload_chunks(file),
    )
    # Kick off async processing; falls back to inline processing if the broker
    # is unreachable (see enqueue_scan).
    enqueue_scan(file_item.id)
    return file_item


@router.get("/files/{file_id}", response_model=FileItem)
async def get_file_view(file_id: str, file_service: FileService = Depends(get_file_service)):
    return await file_service.get(file_id)


@router.patch("/files/{file_id}", response_model=FileItem)
async def update_file_view(
    file_id: str,
    payload: FileUpdate,
    file_service: FileService = Depends(get_file_service),
):
    return await file_service.update_title(file_id, payload.title)


@router.get("/files/{file_id}/download")
async def download_file_view(
    file_id: str, file_service: FileService = Depends(get_file_service)
):
    file_item, stored_path = await file_service.get_download(file_id)
    return FileResponse(
        path=stored_path,
        media_type=file_item.mime_type,
        filename=file_item.original_name,
    )


@router.delete("/files/{file_id}", status_code=204)
async def delete_file_view(file_id: str, file_service: FileService = Depends(get_file_service)):
    await file_service.delete(file_id)
