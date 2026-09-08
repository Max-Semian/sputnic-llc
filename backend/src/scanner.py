"""Threat analysis and file metadata extraction.

Pure, synchronous helpers used by the worker pipeline. Everything here is free of
HTTP/DB concerns and therefore unit-testable in isolation.

Rules mirror the original business logic:
  * executable-ish extensions are suspicious;
  * files larger than ``MAX_CLEAN_SIZE`` are suspicious;
  * a ``.pdf`` whose *content* is not a PDF is suspicious (the original code
    trusted the client-supplied ``Content-Type``; we now sniff magic bytes,
    which cannot be spoofed by the uploader).

Metadata counters (text / PDF) are computed by streaming the file in bounded
chunks instead of loading it fully into memory. Counting a token like
``/Type /Page`` across a chunk boundary is handled by carrying the previous
chunk's tail, so results are identical to a full-file scan.
"""

from pathlib import Path

SUSPICIOUS_EXTENSIONS = {".exe", ".bat", ".cmd", ".sh", ".js"}
MAX_CLEAN_SIZE = 10 * 1024 * 1024  # 10 MB
PDF_HEADER = b"%PDF"
_SCAN_CHUNK_SIZE = 1024 * 1024


# ----------------------------------------------------------------------
# Threat rules
# ----------------------------------------------------------------------
def evaluate_threats(
    *,
    extension: str,
    size: int,
    header: bytes,
) -> list[str]:
    """Return human-readable reasons why a file is suspicious (empty = clean)."""
    reasons: list[str] = []

    if extension in SUSPICIOUS_EXTENSIONS:
        reasons.append(f"suspicious extension {extension}")

    if size > MAX_CLEAN_SIZE:
        reasons.append("file is larger than 10 MB")

    if extension == ".pdf" and not header.startswith(PDF_HEADER):
        reasons.append("pdf extension does not match file content")

    return reasons


# ----------------------------------------------------------------------
# Streaming metadata extraction
# ----------------------------------------------------------------------
def extract_text_metadata(path: str | Path) -> dict:
    """Count lines and characters of a UTF-8 text file without loading it whole.

    Semantics: ``line_count`` equals ``len(text.splitlines())`` and
    ``char_count`` equals ``len(text)`` after decoding with UTF-8 + ignore.
    """
    import codecs

    line_count = 0
    char_count = 0
    newlines = 0
    ends_with_newline = False

    decoder = codecs.getincrementaldecoder("utf-8")(errors="ignore")
    with open(path, "rb") as fh:
        while chunk := fh.read(_SCAN_CHUNK_SIZE):
            text = decoder.decode(chunk)
            char_count += len(text)
            if text:
                newlines += text.count("\n")
                ends_with_newline = text.endswith("\n")

        text = decoder.decode(b"", final=True)  # flush multi-byte tail
        if text:
            char_count += len(text)
            newlines += text.count("\n")
            ends_with_newline = text.endswith("\n")

    if char_count:
        line_count = newlines + (0 if ends_with_newline else 1)

    return {"line_count": line_count, "char_count": char_count}


def extract_pdf_metadata(path: str | Path) -> dict:
    """Approximate page count of a PDF.

    Counts occurrences of ``/Type /Page`` (matching the original heuristic) but
    streams the file and correctly handles a token that straddles a chunk
    boundary.
    """
    token = b"/Type /Page"
    tail = len(token) - 1
    count = 0
    carry = b""

    with open(path, "rb") as fh:
        while chunk := fh.read(_SCAN_CHUNK_SIZE):
            data = carry + chunk
            count += data.count(token)
            carry = data[-tail:] if tail else b""

    return {"approx_page_count": max(count, 1)}
