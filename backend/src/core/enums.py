"""Domain enums (string-valued so they map 1:1 to DB columns and JSON)."""

from enum import StrEnum


class ProcessingStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class ScanStatus(StrEnum):
    CLEAN = "clean"
    SUSPICIOUS = "suspicious"
    FAILED = "failed"


class AlertLevel(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
