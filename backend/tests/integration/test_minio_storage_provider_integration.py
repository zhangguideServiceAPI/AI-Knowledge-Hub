from contextlib import suppress
from io import BytesIO
from os import getenv
from uuid import uuid4

import boto3
import pytest
from botocore.client import BaseClient
from botocore.config import Config

from app.core.config import settings
from app.storage.exceptions import StorageOperationError
from app.storage.minio import MinIOStorageProvider

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        getenv("RUN_MINIO_INTEGRATION_TESTS") != "1",
        reason="Set RUN_MINIO_INTEGRATION_TESTS=1 to run real MinIO tests.",
    ),
]


def _get_minio_config() -> tuple[str, str, str, str]:
    endpoint = settings.STORAGE_MINIO_ENDPOINT
    access_key = settings.STORAGE_MINIO_ACCESS_KEY
    secret_key = settings.STORAGE_MINIO_SECRET_KEY
    bucket = settings.STORAGE_MINIO_BUCKET

    assert endpoint is not None
    assert access_key is not None
    assert secret_key is not None
    assert bucket is not None

    return (
        str(endpoint),
        access_key,
        secret_key.get_secret_value(),
        bucket,
    )


def _create_minio_client(
    *,
    endpoint: str,
    access_key: str,
    secret_key: str,
) -> BaseClient:
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="us-east-1",
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
        ),
    )


def test_real_minio_provider_round_trip() -> None:
    endpoint, access_key, secret_key, bucket = _get_minio_config()
    client = _create_minio_client(
        endpoint=endpoint,
        access_key=access_key,
        secret_key=secret_key,
    )
    provider = MinIOStorageProvider(
        client=client,
        bucket=bucket,
    )
    object_key = f"integration-tests/{uuid4().hex}.bin"
    content = b"real minio integration content"

    try:
        assert provider.exists(object_key) is False

        provider.put(
            object_key,
            BytesIO(content),
        )
        assert provider.exists(object_key) is True

        stream = provider.open(object_key)
        try:
            assert stream.read() == content
        finally:
            stream.close()

        provider.delete(object_key)
        assert provider.exists(object_key) is False

        # 第二次删除仍成功，验证 Provider 的幂等删除契约。
        provider.delete(object_key)
    finally:
        # 测试中途失败时，也尽量清理本测试创建的唯一对象。
        with suppress(StorageOperationError):
            provider.delete(object_key)
        client.close()


def test_real_minio_rejects_invalid_credentials() -> None:
    endpoint, access_key, secret_key, bucket = _get_minio_config()
    client = _create_minio_client(
        endpoint=endpoint,
        access_key=access_key,
        secret_key=f"{secret_key}-invalid",
    )
    provider = MinIOStorageProvider(
        client=client,
        bucket=bucket,
    )

    try:
        with pytest.raises(StorageOperationError):
            provider.exists(f"integration-tests/{uuid4().hex}.bin")
    finally:
        client.close()


def test_real_minio_maps_missing_bucket_to_operation_error() -> None:
    endpoint, access_key, secret_key, _ = _get_minio_config()
    client = _create_minio_client(
        endpoint=endpoint,
        access_key=access_key,
        secret_key=secret_key,
    )
    provider = MinIOStorageProvider(
        client=client,
        bucket=f"missing-integration-{uuid4().hex}",
    )

    try:
        with pytest.raises(StorageOperationError):
            provider.exists("missing-object.bin")
    finally:
        client.close()
