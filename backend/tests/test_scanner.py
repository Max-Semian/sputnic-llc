"""Unit tests for scanner rules and streaming metadata extraction."""

import pytest

from src.domain import scanning as scanner

TOKEN = b"/Type /Page"


# ----------------------------------------------------------------------
# Threat rules
# ----------------------------------------------------------------------
@pytest.mark.parametrize("extension", [".exe", ".bat", ".cmd", ".sh", ".js"])
def test_suspicious_extensions_are_flagged(extension):
    reasons = scanner.evaluate_threats(extension=extension, size=100, header=b"anything")
    assert f"suspicious extension {extension}" in reasons
    assert reasons


def test_clean_txt_is_not_suspicious():
    reasons = scanner.evaluate_threats(
        extension=".txt", size=100, header=b"hello world"
    )
    assert reasons == []


def test_large_file_is_flagged():
    reasons = scanner.evaluate_threats(
        extension=".txt",
        size=scanner.MAX_CLEAN_SIZE + 1,
        header=b"x",
    )
    assert "file is larger than 10 MB" in reasons


def test_pdf_with_non_pdf_content_is_flagged():
    # An .exe renamed to .pdf: header is MZ, declared content type lies.
    reasons = scanner.evaluate_threats(
        extension=".pdf", size=100, header=b"MZ\x90\x00"
    )
    assert "pdf extension does not match file content" in reasons


def test_real_pdf_is_clean_even_with_spoofed_mime():
    # Content sniffing must win over the client-supplied Content-Type.
    reasons = scanner.evaluate_threats(
        extension=".pdf", size=100, header=scanner.PDF_HEADER + b"-1.7"
    )
    assert reasons == []


# ----------------------------------------------------------------------
# Streaming text metadata
# ----------------------------------------------------------------------
def _write(tmp_path, data: bytes):
    path = tmp_path / "sample.txt"
    path.write_bytes(data)
    return path


@pytest.mark.parametrize(
    ("data", "lines", "chars"),
    [
        (b"", 0, 0),
        (b"one", 1, 3),
        (b"a\nb", 2, 3),
        (b"a\nb\n", 2, 4),
        (b"\xd0\xbf\xd1\x80\xd0\xb8\xd0\xb2\xd0\xb5\xd1\x82\n\xd0\xbc\xd0\xb8\xd1\x80", 2, 10),
    ],
)
def test_text_metadata_counts(tmp_path, data, lines, chars):
    stats = scanner.extract_text_metadata(_write(tmp_path, data))
    assert stats == {"line_count": lines, "char_count": chars}


# ----------------------------------------------------------------------
# Streaming PDF metadata (incl. token across chunk boundary)
# ----------------------------------------------------------------------
def _pdf_bytes(num_tokens: int) -> bytes:
    # 1MB-ish payload so multiple reads are needed with the default chunk size
    body = b"obj\n" + TOKEN + b"\nendobj\n" + b"\x00" * (256 * 1024)
    return b"%PDF-1.7\n" + body * num_tokens


def test_pdf_metadata_counts_tokens(tmp_path):
    content = _pdf_bytes(3)
    path = tmp_path / "sample.pdf"
    path.write_bytes(content)
    stats = scanner.extract_pdf_metadata(path)
    assert stats["approx_page_count"] == content.count(TOKEN)


def test_pdf_metadata_token_crosses_chunk_boundary(tmp_path, monkeypatch):
    """The classic pitfall: a token split across a chunk boundary must still count."""
    monkeypatch.setattr(scanner, "SCAN_CHUNK_SIZE", 7)
    # token starts 5 bytes before a chunk boundary, i.e. it straddles two reads
    content = b"x" * 5 + TOKEN + b"y" * 20
    path = tmp_path / "sample.pdf"
    path.write_bytes(content)
    assert scanner.extract_pdf_metadata(path)["approx_page_count"] == content.count(TOKEN)


def test_pdf_metadata_min_one_page(tmp_path):
    path = tmp_path / "empty.pdf"
    path.write_bytes(b"%PDF-1.7")
    assert scanner.extract_pdf_metadata(path)["approx_page_count"] == 1
