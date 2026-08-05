from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from app.storage import readiness as storage_readiness


def test_local_storage_is_ready_without_minio_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    minio_client_factory = Mock()
    bucket_resolver = Mock()

    monkeypatch.setattr(
        storage_readiness.settings,
        "STORAGE_PROVIDER",
        "local",
    )
    monkeypatch.setattr(
        storage_readiness,
        "get_minio_readiness_client",
        minio_client_factory,
    )
    monkeypatch.setattr(
        storage_readiness,
        "get_storage_bucket",
        bucket_resolver,
    )

    assert storage_readiness.is_storage_ready() is True
    minio_client_factory.assert_not_called()
    bucket_resolver.assert_not_called()


def test_minio_storage_is_ready_when_bucket_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = Mock()

    monkeypatch.setattr(
        storage_readiness.settings,
        "STORAGE_PROVIDER",
        "minio",
    )
    monkeypatch.setattr(
        storage_readiness,
        "get_minio_readiness_client",
        lambda: client,
    )
    monkeypatch.setattr(
        storage_readiness,
        "get_storage_bucket",
        lambda: "test-files",
    )

    assert storage_readiness.is_storage_ready() is True
    client.head_bucket.assert_called_once_with(
        Bucket="test-files",
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
            "HeadBucket",
        ),
    ],
)
def test_minio_storage_is_not_ready_when_bucket_check_fails(
    monkeypatch: pytest.MonkeyPatch,
    sdk_error: Exception,
) -> None:
    client = Mock()
    client.head_bucket.side_effect = sdk_error

    monkeypatch.setattr(
        storage_readiness.settings,
        "STORAGE_PROVIDER",
        "minio",
    )
    monkeypatch.setattr(
        storage_readiness,
        "get_minio_readiness_client",
        lambda: client,
    )
    monkeypatch.setattr(
        storage_readiness,
        "get_storage_bucket",
        lambda: "test-files",
    )

    assert storage_readiness.is_storage_ready() is False
