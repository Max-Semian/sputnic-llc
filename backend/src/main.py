"""FastAPI application factory.

The previous single module ``app.py``/``service.py`` mix created engines as
module-level side effects. Now the app is assembled from explicit layers:
``config`` -> ``api`` routes -> ``services`` -> ``storage``/``db``.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.routes import router
from src.config import Settings, get_settings
from src.db import make_async_session_factory
from src.errors import AppError
from src.storage import LocalStorage

logger = logging.getLogger(__name__)


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
        app.state.settings = settings
        app.state.session_factory = session_factory
        app.state.engine = engine
        app.state.storage = storage
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(
        title="File sharing MVP",
        description="Upload files, scan them for suspicious content, receive alerts.",
        version="0.2.0",
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
