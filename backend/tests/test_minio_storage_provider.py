from io import BytesIO
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from app.storage.exceptions import (
    InvalidObjectKeyError,
    StorageObjectNotFoundError,
    StorageOperationError,
)
from app.storage.minio import MinIOStorageProvider


def test_constructor_rejects_empty_bucket() -> None:
    with pytest.raises(ValueError, match="Bucket name cannot be empty"):
        MinIOStorageProvider(
            client=Mock(),
            bucket="",
        )


def test_put_uploads_source_to_configured_bucket() -> None:
    client = Mock()
    provider = MinIOStorageProvider(
        client=client,
        bucket="test-files",
    )
    source = BytesIO(b"file content")

    provider.put(
        "users/42/file-id",
        source,
    )

    client.upload_fileobj.assert_called_once_with(
        Fileobj=source,
        Bucket="test-files",
        Key="users/42/file-id",
    )


@pytest.mark.parametrize(
    "sdk_error",
    [
        EndpointConnectionError(
            endpoint_url="http://127.0.0.1:9000",
        ),
        ClientError(
            {
                "Error": {
                    "Code": "AccessDenied",
                    "Message": "Access denied.",
                }
            },
            "PutObject",
        ),
    ],
)
def test_put_maps_boto_errors_to_storage_operation_error(
    sdk_error: Exception,
) -> None:
    client = Mock()
    client.upload_fileobj.side_effect = sdk_error
    provider = MinIOStorageProvider(
        client=client,
        bucket="test-files",
    )

    with pytest.raises(StorageOperationError) as error:
        provider.put(
            "users/42/file-id",
            BytesIO(b"file content"),
        )

    assert error.value.__cause__ is sdk_error


def test_put_rejects_empty_object_key() -> None:
    client = Mock()
    provider = MinIOStorageProvider(
        client=client,
        bucket="test-files",
    )

    with pytest.raises(InvalidObjectKeyError):
        provider.put("", BytesIO(b"file content"))

    client.upload_fileobj.assert_not_called()


def test_open_returns_object_body_stream() -> None:
    client = Mock()
    stream = BytesIO(b"stored content")
    client.get_object.return_value = {
        "Body": stream,
    }
    provider = MinIOStorageProvider(
        client=client,
        bucket="test-files",
    )

    result = provider.open("users/42/file-id")

    assert result is stream
    client.get_object.assert_called_once_with(
        Bucket="test-files",
        Key="users/42/file-id",
    )


def test_open_maps_missing_object_error() -> None:
    client = Mock()
    sdk_error = ClientError(
        {
            "Error": {
                "Code": "NoSuchKey",
                "Message": "Object does not exist.",
            }
        },
        "GetObject",
    )
    client.get_object.side_effect = sdk_error
    provider = MinIOStorageProvider(
        client=client,
        bucket="test-files",
    )

    with pytest.raises(StorageObjectNotFoundError) as error:
        provider.open("users/42/missing-file")

    assert error.value.__cause__ is sdk_error


@pytest.mark.parametrize(
    "sdk_error",
    [
        EndpointConnectionError(
            endpoint_url="http://127.0.0.1:9000",
        ),
        ClientError(
            {
                "Error": {
                    "Code": "AccessDenied",
                    "Message": "Access denied.",
                }
            },
            "GetObject",
        ),
    ],
)
def test_open_maps_boto_errors_to_storage_operation_error(
    sdk_error: Exception,
) -> None:
    client = Mock()
    client.get_object.side_effect = sdk_error
    provider = MinIOStorageProvider(
        client=client,
        bucket="test-files",
    )

    with pytest.raises(StorageOperationError) as error:
        provider.open("users/42/file-id")

    assert error.value.__cause__ is sdk_error


def test_open_rejects_response_without_body() -> None:
    client = Mock()
    client.get_object.return_value = {}
    provider = MinIOStorageProvider(
        client=client,
        bucket="test-files",
    )

    with pytest.raises(StorageOperationError) as error:
        provider.open("users/42/file-id")

    assert isinstance(error.value.__cause__, KeyError)


def test_open_rejects_empty_object_key() -> None:
    client = Mock()
    provider = MinIOStorageProvider(
        client=client,
        bucket="test-files",
    )

    with pytest.raises(InvalidObjectKeyError):
        provider.open("")

    client.get_object.assert_not_called()


def test_exists_returns_true_when_object_exists() -> None:
    client = Mock()
    client.head_object.return_value = {}
    provider = MinIOStorageProvider(
        client=client,
        bucket="test-files",
    )

    result = provider.exists("users/42/file-id")

    assert result is True
    client.head_object.assert_called_once_with(
        Bucket="test-files",
        Key="users/42/file-id",
    )


def test_exists_returns_false_when_object_is_missing() -> None:
    client = Mock()
    sdk_error = ClientError(
        {
            "Error": {
                "Code": "NoSuchKey",
                "Message": "Object does not exist.",
            }
        },
        "HeadObject",
    )
    client.head_object.side_effect = sdk_error
    provider = MinIOStorageProvider(
        client=client,
        bucket="test-files",
    )

    result = provider.exists("users/42/missing-file")

    assert result is False


@pytest.mark.parametrize(
    "sdk_error",
    [
        EndpointConnectionError(
            endpoint_url="http://127.0.0.1:9000",
        ),
        ClientError(
            {
                "Error": {
                    "Code": "AccessDenied",
                    "Message": "Access denied.",
                }
            },
            "HeadObject",
        ),
    ],
)
def test_exists_maps_boto_errors_to_storage_operation_error(
    sdk_error: Exception,
) -> None:
    client = Mock()
    client.head_object.side_effect = sdk_error
    provider = MinIOStorageProvider(
        client=client,
        bucket="test-files",
    )

    with pytest.raises(StorageOperationError) as error:
        provider.exists("users/42/file-id")

    assert error.value.__cause__ is sdk_error


def test_exists_rejects_empty_object_key() -> None:
    client = Mock()
    provider = MinIOStorageProvider(
        client=client,
        bucket="test-files",
    )

    with pytest.raises(InvalidObjectKeyError):
        provider.exists("")

    client.head_object.assert_not_called()


def test_delete_removes_object() -> None:
    client = Mock()
    client.delete_object.return_value = {}
    provider = MinIOStorageProvider(
        client=client,
        bucket="test-files",
    )

    provider.delete("users/42/file-id")

    client.delete_object.assert_called_once_with(
        Bucket="test-files",
        Key="users/42/file-id",
    )


def test_delete_is_idempotent_when_object_is_missing() -> None:
    client = Mock()
    sdk_error = ClientError(
        {
            "Error": {
                "Code": "NoSuchKey",
                "Message": "Object does not exist.",
            }
        },
        "DeleteObject",
    )
    client.delete_object.side_effect = sdk_error
    provider = MinIOStorageProvider(
        client=client,
        bucket="test-files",
    )

    provider.delete("users/42/missing-file")

    client.delete_object.assert_called_once_with(
        Bucket="test-files",
        Key="users/42/missing-file",
    )


@pytest.mark.parametrize(
    "sdk_error",
    [
        EndpointConnectionError(
            endpoint_url="http://127.0.0.1:9000",
        ),
        ClientError(
            {
                "Error": {
                    "Code": "AccessDenied",
                    "Message": "Access denied.",
                }
            },
            "DeleteObject",
        ),
    ],
)
def test_delete_maps_boto_errors_to_storage_operation_error(
    sdk_error: Exception,
) -> None:
    client = Mock()
    client.delete_object.side_effect = sdk_error
    provider = MinIOStorageProvider(
        client=client,
        bucket="test-files",
    )

    with pytest.raises(StorageOperationError) as error:
        provider.delete("users/42/file-id")

    assert error.value.__cause__ is sdk_error


def test_delete_rejects_empty_object_key() -> None:
    client = Mock()
    provider = MinIOStorageProvider(
        client=client,
        bucket="test-files",
    )

    with pytest.raises(InvalidObjectKeyError):
        provider.delete("")

    client.delete_object.assert_not_called()
