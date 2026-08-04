from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import BinaryIO
from unicodedata import category

from app.storage.exceptions import (
    EmptyFileError,
    FileTooLargeError,
    InvalidFileNameError,
    UnsupportedFileTypeError,
)


# frozenset 是创建后不能修改的 set，避免运行时误改允许列表。
_ALLOWED_EXTENSIONS: dict[str, frozenset[str]] = {
    "application/pdf": frozenset({".pdf"}),
    "image/png": frozenset({".png"}),
    "image/jpeg": frozenset({".jpg", ".jpeg"}),
}


# @dataclass 是帮我们自动生成构造方法 frozen=True 表示创建后不能修改
@dataclass(frozen=True)
class InspectedUpload:
    original_filename: str
    content_type: str
    size_bytes: int
    sha256: str


def validate_upload_metadata(
    original_filename: str | None,
    content_type: str | None,
) -> tuple[str, str]:
    # strip() 去掉文件名首尾空格。
    filename = (original_filename or "").strip()

    if (
        not filename
        or len(filename) > 255
        or filename in {".", ".."}
        or "/" in filename
        or "\\" in filename
        # any() 中只要有一个字符属于控制字符，结果就是 True。
        or any(category(character) == "Cc" for character in filename)
    ):
        raise InvalidFileNameError()

    normalized_content_type = (
        (content_type or "").split(";", maxsplit=1)[0].strip().lower()
    )
    allowed_extensions = _ALLOWED_EXTENSIONS.get(normalized_content_type)

    if allowed_extensions is None:
        raise UnsupportedFileTypeError()

    # Path 这里只提取扩展名，不会访问磁盘。
    extension = Path(filename).suffix.lower()

    if extension not in allowed_extensions:
        raise UnsupportedFileTypeError()

    return filename, normalized_content_type


def _matches_file_signature(
    content_type: str,
    prefix: bytes,
) -> bool:
    if content_type == "application/pdf":
        return b"%PDF-" in prefix[:1024]

    if content_type == "image/png":
        return prefix.startswith(b"\x89PNG\r\n\x1a\n")

    if content_type == "image/jpeg":
        return prefix.startswith(b"\xff\xd8\xff")

    return False


# 参数中的单独 * 表示后面的参数必须写名字：
def inspect_upload(
    source: BinaryIO,
    *,
    original_filename: str | None,
    content_type: str | None,
    max_upload_size: int,
    chunk_size: int,
) -> InspectedUpload:
    if max_upload_size <= 0:
        raise ValueError("Maximum upload size must be greater than zero.")

    if chunk_size <= 0:
        raise ValueError("Upload chunk size must be greater than zero.")

    filename, normalized_content_type = validate_upload_metadata(
        original_filename,
        content_type,
    )

    digest = sha256()
    total_size = 0
    prefix = bytearray()

    while True:
        chunk = source.read(chunk_size)

        if not chunk:
            break

        total_size += len(chunk)

        if total_size > max_upload_size:
            raise FileTooLargeError()

        digest.update(chunk)

        remaining_prefix_size = 1024 - len(prefix)

        if remaining_prefix_size > 0:
            # 例如已经保存 900 Bytes，只再取 124 Bytes，保证最多 1024。
            prefix.extend(chunk[:remaining_prefix_size])

    if total_size == 0:
        raise EmptyFileError()

    if not _matches_file_signature(
        normalized_content_type,
        bytes(prefix),
    ):
        raise UnsupportedFileTypeError()

    source.seek(0)

    return InspectedUpload(
        original_filename=filename,
        content_type=normalized_content_type,
        size_bytes=total_size,
        sha256=digest.hexdigest(),
    )
