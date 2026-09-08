"""HTTP endpoints. Thin presentation layer: parses input, calls services,
maps domain errors (via the app-level handler) and returns DTOs.
"""

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src import services
from src.api.deps import get_session, get_storage
from src.schemas import AlertItem, FileItem, FileUpdate
from src.storage import LocalStorage
from src.worker.tasks import enqueue_scan

router = APIRouter()

_UPLOAD_CHUNK = 1024 * 1024


async def _upload_chunks(upload: UploadFile, chunk_size: int = _UPLOAD_CHUNK) -> AsyncIterator[bytes]:
    """Read an UploadFile in bounded chunks instead of loading it fully."""
    while True:
        chunk = await upload.read(chunk_size)
        if not chunk:
            break
        yield chunk


@router.get("/files", response_model=list[FileItem])
async def list_files_view(session: AsyncSession = Depends(get_session)):
    return await services.list_files(session)


@router.get("/alerts", response_model=list[AlertItem])
async def list_alerts_view(session: AsyncSession = Depends(get_session)):
    return await services.list_alerts(session)


@router.post("/files", response_model=FileItem, status_code=201)
async def create_file_view(
    request: Request,
    title: str = Form(...),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    storage: LocalStorage = Depends(get_storage),
):
    file_item = await services.create_file(
        session,
        storage,
        title=title,
        original_name=file.filename or "",
        content_type=file.content_type,
        chunks=_upload_chunks(file),
    )
    # Kick off the async processing pipeline. If the broker is unreachable the
    # file is processed inline (see enqueue_scan) instead of staying stuck.
    enqueue_scan(file_item.id)
    return file_item


@router.get("/files/{file_id}", response_model=FileItem)
async def get_file_view(file_id: str, session: AsyncSession = Depends(get_session)):
    return await services.get_file(session, file_id)


@router.patch("/files/{file_id}", response_model=FileItem)
async def update_file_view(
    file_id: str,
    payload: FileUpdate,
    session: AsyncSession = Depends(get_session),
):
    return await services.update_file(session, file_id=file_id, title=payload.title)


@router.get("/files/{file_id}/download")
async def download_file_view(
    file_id: str,
    session: AsyncSession = Depends(get_session),
    storage: LocalStorage = Depends(get_storage),
):
    file_item, stored_path = await services.get_download(session, storage, file_id)
    return FileResponse(
        path=stored_path,
        media_type=file_item.mime_type,
        filename=file_item.original_name,
    )


@router.delete("/files/{file_id}", status_code=204)
async def delete_file_view(
    file_id: str,
    session: AsyncSession = Depends(get_session),
    storage: LocalStorage = Depends(get_storage),
):
    await services.delete_file(session, storage, file_id)
