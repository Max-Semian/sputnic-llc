"""HTTP request/response schemas (presentation layer)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FileItem(BaseModel):
    """Public representation of a stored file (unchanged shape)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    original_name: str
    mime_type: str
    size: int
    processing_status: str
    scan_status: str | None
    scan_details: str | None
    metadata_json: dict | None
    requires_attention: bool
    created_at: datetime
    updated_at: datetime


class FileUpdate(BaseModel):
    """PATCH payload; length-validated -> HTTP 422 instead of a DB 500."""

    title: str = Field(min_length=1, max_length=255)


class AlertItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    file_id: str
    level: str
    message: str
    created_at: datetime
