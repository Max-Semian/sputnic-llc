"""Domain-level errors.

The application/service layer signals failures with these exceptions instead of
raising FastAPI's ``HTTPException`` directly. The API layer maps them to HTTP
responses, which keeps the domain free of transport concerns.
"""


class AppError(Exception):
    status_code: int = 400
    detail: str = "Unexpected error"

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(detail or self.detail)
        self.detail = detail or self.detail


class NotFoundError(AppError):
    status_code = 404
    detail = "Not found"


class FileNotFoundError(NotFoundError):
    detail = "File not found"


class StoredFileMissingError(NotFoundError):
    detail = "Stored file not found"


class EmptyFileError(AppError):
    status_code = 400
    detail = "File is empty"


class FileTooLargeError(AppError):
    status_code = 413
    detail = "File is too large"


class StorageError(AppError):
    status_code = 500
    detail = "Storage operation failed"
