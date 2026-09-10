"""FastAPI application factory (presentation layer).

Wiring order: core config -> infrastructure (storage, DB, UoW) -> application
services -> routes. Dependencies are attached to ``app.state`` and injected via
``src.presentation.deps``.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.application.services.alert_service import AlertService
from src.application.services.file_service import FileService
from src.core.config import Settings, get_settings
from src.core.errors import AppError
from src.infrastructure.db import make_async_session_factory
from src.infrastructure.repositories import SqlAlchemyUnitOfWork
from src.infrastructure.storage import LocalStorage
from src.presentation.routes import router


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    storage = LocalStorage(
        settings.storage_dir,
        max_size=settings.max_upload_size,
        chunk_size=settings.chunk_size,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        session_factory, engine = make_async_session_factory(settings.async_database_url)
        uow_factory = lambda: SqlAlchemyUnitOfWork(session_factory)  # noqa: E731

        app.state.settings = settings
        app.state.session_factory = session_factory
        app.state.engine = engine
        app.state.storage = storage
        app.state.file_service = FileService(uow_factory, storage)
        app.state.alert_service = AlertService(uow_factory)
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(
        title="File sharing MVP",
        description="Upload files, scan them for suspicious content, receive alerts.",
        version="0.3.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):  # noqa: ANN001
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    return app


app = create_app()
