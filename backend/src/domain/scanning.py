"""Threat analysis and metadata extraction (domain layer).

Pure/synchronous helpers with no DB or HTTP concerns; used by
``ProcessingService``. Rules mirror the original business logic:
  * executable-ish extensions are suspicious;
  * files larger than MAX_CLEAN_SIZE are suspicious;
  * a .pdf whose content is not a PDF is suspicious (magic-byte sniffing
    instead of trusting the client-supplied Content-Type).

Metadata counters stream the file in bounded chunks; the /Type /Page token is
counted with chunk-boundary carry so results equal a full-file scan.
"""

from pathlib import Path

SUSPICIOUS_EXTENSIONS = {".exe", ".bat", ".cmd", ".sh", ".js"}
MAX_CLEAN_SIZE = 10 * 1024 * 1024  # 10 MB
PDF_HEADER = b"%PDF"
SCAN_CHUNK_SIZE = 1024 * 1024
PDF_PAGE_TOKEN = b"/Type /Page"


def evaluate_threats(*, extension: str, size: int, header: bytes) -> list[str]:
    """Return human-readable reasons why a file is suspicious (empty = clean)."""
    reasons: list[str] = []
    if extension in SUSPICIOUS_EXTENSIONS:
        reasons.append(f"suspicious extension {extension}")
    if size > MAX_CLEAN_SIZE:
        reasons.append("file is larger than 10 MB")
    if extension == ".pdf" and not header.startswith(PDF_HEADER):
        reasons.append("pdf extension does not match file content")
    return reasons


def read_header(path: str | Path, size: int = 4096) -> bytes:
    """Read the first ``size`` bytes (empty bytes if the file is missing)."""
    try:
        with open(path, "rb") as fh:
            return fh.read(size)
    except FileNotFoundError:
        return b""


def extract_text_metadata(path: str | Path) -> dict:
    """Count lines/characters of a UTF-8 text file without loading it whole."""
    import codecs

    line_count = 0
    char_count = 0
    newlines = 0
    ends_with_newline = False

    decoder = codecs.getincrementaldecoder("utf-8")(errors="ignore")
    with open(path, "rb") as fh:
        while chunk := fh.read(SCAN_CHUNK_SIZE):
            text = decoder.decode(chunk)
            char_count += len(text)
            if text:
                newlines += text.count("\n")
                ends_with_newline = text.endswith("\n")
        text = decoder.decode(b"", final=True)
        if text:
            char_count += len(text)
            newlines += text.count("\n")
            ends_with_newline = text.endswith("\n")

    if char_count:
        line_count = newlines + (0 if ends_with_newline else 1)
    return {"line_count": line_count, "char_count": char_count}


def extract_pdf_metadata(path: str | Path) -> dict:
    """Approximate page count of a PDF (streaming, boundary-safe token count)."""
    tail = len(PDF_PAGE_TOKEN) - 1
    count = 0
    carry = b""
    with open(path, "rb") as fh:
        while chunk := fh.read(SCAN_CHUNK_SIZE):
            data = carry + chunk
            count += data.count(PDF_PAGE_TOKEN)
            carry = data[-tail:] if tail else b""
    return {"approx_page_count": max(count, 1)}
