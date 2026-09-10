"""FastAPI dependency providers (presentation layer)."""

from fastapi import Request

from src.application.services.alert_service import AlertService
from src.application.services.file_service import FileService
from src.infrastructure.storage import LocalStorage


def get_file_service(request: Request) -> FileService:
    return request.app.state.file_service


def get_alert_service(request: Request) -> AlertService:
    return request.app.state.alert_service


def get_storage(request: Request) -> LocalStorage:
    return request.app.state.storage
