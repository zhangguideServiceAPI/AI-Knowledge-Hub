from typing import BinaryIO, cast

from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError

from app.storage.exceptions import (
    InvalidObjectKeyError,
    StorageOperationError,
    StorageObjectNotFoundError,
)

_MISSING_OBJECT_ERROR_CODES = frozenset(
    {
        "404",
        "NoSuchKey",
        "NotFound",
    }
)


def _validate_object_key(object_key: str) -> None:
    if not object_key:
        raise InvalidObjectKeyError("Object key cannot be empty.")


def _is_missing_object_error(error: ClientError) -> bool:
    error_code = error.response.get("Error", {}).get("Code")
    return error_code in _MISSING_OBJECT_ERROR_CODES


class MinIOStorageProvider:
    def __init__(
        self,
        client: BaseClient,
        bucket: str,
    ) -> None:
        if not bucket:
            raise ValueError("Bucket name cannot be empty.")

        self._client = client
        self._bucket = bucket

    def put(
        self,
        object_key: str,
        source: BinaryIO,
    ) -> None:
        _validate_object_key(object_key)

        try:
            self._client.upload_fileobj(
                Fileobj=source,
                Bucket=self._bucket,
                Key=object_key,
            )
        except (BotoCoreError, ClientError) as error:
            raise StorageOperationError("Failed to upload storage object.") from error

    def open(
        self,
        object_key: str,
    ) -> BinaryIO:
        _validate_object_key(object_key)

        try:
            response = self._client.get_object(
                Bucket=self._bucket,
                Key=object_key,
            )
        except ClientError as error:
            if _is_missing_object_error(error):
                raise StorageObjectNotFoundError(
                    "Storage object does not exist."
                ) from error

            raise StorageOperationError("Failed to open storage object.") from error
        except BotoCoreError as error:
            raise StorageOperationError("Failed to open storage object.") from error

        try:
            body = response["Body"]
        except KeyError as error:
            raise StorageOperationError(
                "Storage response did not include object body."
            ) from error

        return cast(BinaryIO, body)

    def exists(
        self,
        object_key: str,
    ) -> bool:
        _validate_object_key(object_key)

        try:
            self._client.head_object(
                Bucket=self._bucket,
                Key=object_key,
            )
        except ClientError as error:
            if _is_missing_object_error(error):
                return False

            raise StorageOperationError("Failed to check storage object.") from error
        except BotoCoreError as error:
            raise StorageOperationError("Failed to check storage object.") from error

        return True

    def delete(
        self,
        object_key: str,
    ) -> None:
        _validate_object_key(object_key)

        try:
            self._client.delete_object(
                Bucket=self._bucket,
                Key=object_key,
            )
        except ClientError as error:
            if _is_missing_object_error(error):
                return

            raise StorageOperationError("Failed to delete storage object.") from error
        except BotoCoreError as error:
            raise StorageOperationError("Failed to delete storage object.") from error
