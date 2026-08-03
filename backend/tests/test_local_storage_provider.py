import pytest

from unittest.mock import Mock
from io import BytesIO
from pathlib import Path


from app.storage.local import LocalStorageProvider
from app.storage.exceptions import (
    InvalidObjectKeyError,
    StorageObjectNotFoundError,
    StorageOperationError,
)


def test_put_open_and_exists_round_trip(tmp_path: Path) -> None:
    provider = LocalStorageProvider(
        root=tmp_path,
        chunk_size=4,
    )
    content = b"hello local storage"

    provider.put(
        "users/42/report.bin",
        BytesIO(content),
    )

    assert provider.exists("users/42/report.bin") is True

    with provider.open("users/42/report.bin") as stored_file:
        assert stored_file.read() == content


@pytest.mark.parametrize(
    "object_key",
    ["", ".", "../escape.bin", "/escape.bin"],
)
def test_rejects_invalid_object_key(
    tmp_path: Path,
    object_key: str,
) -> None:
    provider = LocalStorageProvider(tmp_path, chunk_size=4)

    with pytest.raises(InvalidObjectKeyError):
        provider.put(object_key, BytesIO(b"unsafe"))


def test_open_raises_when_object_is_missing(tmp_path: Path) -> None:
    provider = LocalStorageProvider(tmp_path, chunk_size=4)

    with pytest.raises(StorageObjectNotFoundError):
        provider.open("missing.bin")


def test_delete_is_idempotent(tmp_path: Path) -> None:
    provider = LocalStorageProvider(tmp_path, chunk_size=4)
    provider.put("object.bin", BytesIO(b"content"))

    provider.delete("object.bin")
    provider.delete("object.bin")

    assert provider.exists("object.bin") is False


def test_put_failure_preserves_existing_object_and_removes_temp_file(
    tmp_path: Path,
) -> None:
    provider = LocalStorageProvider(tmp_path, chunk_size=4)
    provider.put("object.bin", BytesIO(b"old content"))

    source = Mock()
    source.read.side_effect = [
        b"new ",
        OSError("read failed"),
    ]

    with pytest.raises(StorageOperationError):
        provider.put("object.bin", source)

    with provider.open("object.bin") as stored_file:
        assert stored_file.read() == b"old content"

    assert list(tmp_path.glob(".object.bin*.tmp")) == []


@pytest.mark.parametrize("chunk_size", [0, -1])
def test_rejects_non_positive_chunk_size(
    tmp_path: Path,
    chunk_size: int,
) -> None:
    with pytest.raises(ValueError):
        LocalStorageProvider(tmp_path, chunk_size=chunk_size)


def test_initialization_failure_raises_storage_operation_error(
    tmp_path: Path,
) -> None:
    blocking_file = tmp_path / "blocking-file"
    blocking_file.write_bytes(b"not a directory")

    with pytest.raises(StorageOperationError):
        LocalStorageProvider(
            blocking_file / "storage",
            chunk_size=4,
        )
