from hashlib import sha256
from io import BytesIO

import pytest

from app.storage.exceptions import (
    EmptyFileError,
    FileTooLargeError,
    InvalidFileNameError,
    UnsupportedFileTypeError,
)
from app.storage.upload_validation import inspect_upload


def test_inspect_pdf_upload_calculates_size_hash_and_resets_source() -> None:
    content = b"%PDF-1.7\nhello"
    source = BytesIO(content)

    result = inspect_upload(
        source,
        original_filename="report.pdf",
        content_type="application/pdf",
        max_upload_size=1024,
        chunk_size=4,
    )

    assert result.original_filename == "report.pdf"
    assert result.content_type == "application/pdf"
    assert result.size_bytes == len(content)
    assert result.sha256 == sha256(content).hexdigest()
    assert source.tell() == 0


@pytest.mark.parametrize(
    ("filename", "content_type"),
    [("manual.txt", "text/plain"), ("manual.md", "text/markdown")],
)
def test_inspect_utf8_text_upload(
    filename: str,
    content_type: str,
) -> None:
    content = "产品支持 SSO。\n".encode("utf-8")
    source = BytesIO(content)

    result = inspect_upload(
        source,
        original_filename=filename,
        content_type=content_type,
        max_upload_size=1024,
        chunk_size=4,
    )

    assert result.content_type == content_type
    assert result.size_bytes == len(content)
    assert source.tell() == 0


def test_inspect_rejects_invalid_utf8_text() -> None:
    with pytest.raises(UnsupportedFileTypeError):
        inspect_upload(
            BytesIO(b"\xff\xfe"),
            original_filename="invalid.txt",
            content_type="text/plain",
            max_upload_size=1024,
            chunk_size=4,
        )


def test_inspect_rejects_empty_file() -> None:
    source = BytesIO(b"")

    with pytest.raises(EmptyFileError):
        inspect_upload(
            source,
            original_filename="empty.pdf",
            content_type="application/pdf",
            max_upload_size=1024,
            chunk_size=4,
        )


def test_inspect_rejects_file_larger_than_limit() -> None:
    content = b"%PDF-" + b"x" * 10
    source = BytesIO(content)

    with pytest.raises(FileTooLargeError):
        inspect_upload(
            source,
            original_filename="large.pdf",
            content_type="application/pdf",
            max_upload_size=5,
            chunk_size=4,
        )


def test_inspect_rejects_mismatched_file_signature() -> None:
    content = b"not a pdf"
    source = BytesIO(content)

    with pytest.raises(UnsupportedFileTypeError):
        inspect_upload(
            source,
            original_filename="not_a_pdf.pdf",
            content_type="application/pdf",
            max_upload_size=1024,
            chunk_size=4,
        )


@pytest.mark.parametrize(
    "filename",
    [
        None,
        "",
        " ",
        ".",
        "..",
        "../escape.pdf",
        "folder\\file.pdf",
        "bad\nname.pdf",
    ],
)
def test_inspect_rejects_invalid_filename(
    filename: str | None,
) -> None:
    with pytest.raises(InvalidFileNameError):
        inspect_upload(
            BytesIO(b"%PDF-"),
            original_filename=filename,
            content_type="application/pdf",
            max_upload_size=1024,
            chunk_size=4,
        )


def test_inspect_rejects_extension_mismatch() -> None:
    with pytest.raises(UnsupportedFileTypeError):
        inspect_upload(
            BytesIO(b"%PDF-"),
            original_filename="report.png",
            content_type="application/pdf",
            max_upload_size=1024,
            chunk_size=4,
        )
