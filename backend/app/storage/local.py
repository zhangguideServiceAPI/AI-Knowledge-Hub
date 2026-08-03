from contextlib import suppress
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import BinaryIO

from app.storage.exceptions import (
    InvalidObjectKeyError,
    StorageObjectNotFoundError,
    StorageOperationError,
)


class LocalStorageProvider:
    def __init__(self, root: Path, chunk_size: int) -> None:
        if chunk_size <= 0:
            raise ValueError("Chunk size must be greater than zero.")

        try:
            self._root = root.resolve()
            self._root.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise StorageOperationError(
                "Failed to initialize local storage."
            ) from error

        self._chunk_size = chunk_size

    def put(self, object_key: str, source: BinaryIO) -> None:
        temp_path: Path | None = None
        target_path = self._resolve_path(object_key)

        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)

            # 先写同目录临时文件，避免写入中断时暴露半文件。
            with NamedTemporaryFile(
                mode="wb",
                dir=target_path.parent,
                prefix=f".{target_path.name}",
                suffix=".tmp",
                delete=False,
            ) as temp_file:
                temp_path = Path(temp_file.name)

                while True:
                    chunk = source.read(self._chunk_size)
                    if not chunk:
                        break
                    temp_file.write(chunk)
            os.replace(temp_path, target_path)
        except OSError as error:
            if temp_path is not None:
                with suppress(OSError):
                    temp_path.unlink(missing_ok=True)

            raise StorageOperationError("Failed to write storage object.") from error

    def exists(self, object_key: str) -> bool:
        target_path = self._resolve_path(object_key)

        try:
            return target_path.is_file()
        except OSError as error:
            raise StorageOperationError("Failed to check storage object.") from error

    def open(self, object_key: str) -> BinaryIO:
        target_path = self._resolve_path(object_key)

        try:
            return target_path.open("rb")
        except FileNotFoundError as error:
            raise StorageObjectNotFoundError(
                "Storage object does not exist."
            ) from error
        except OSError as error:
            raise StorageOperationError("Failed to open storage object.") from error

    def delete(self, object_key: str) -> None:
        target_path = self._resolve_path(object_key)

        try:
            target_path.unlink(missing_ok=True)
        except OSError as error:
            raise StorageOperationError("Failed to delete storage object.") from error

    def _resolve_path(self, object_key: str) -> Path:
        if not object_key:
            raise InvalidObjectKeyError("Object key cannot be empty.")

        try:
            # 解析现有符号链接后再检查，避免路径逃出 Storage Root。
            target_path = (self._root / object_key).resolve()
        except OSError as error:
            raise StorageOperationError(
                "Failed to resolve storage object path."
            ) from error

        if target_path == self._root or not target_path.is_relative_to(self._root):
            raise InvalidObjectKeyError("Object key escapes storage root.")

        return target_path
