from pathlib import Path
from unittest.mock import Mock
from pydantic import SecretStr
import pytest

from app.storage import factory as storage_factory
from app.storage.local import LocalStorageProvider
from app.storage.minio import MinIOStorageProvider


def test_get_storage_provider_returns_cached_local_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    boto_client_factory = Mock()

    monkeypatch.setattr(
        storage_factory.settings,
        "STORAGE_PROVIDER",
        "local",
    )
    monkeypatch.setattr(
        storage_factory.settings,
        "STORAGE_LOCAL_ROOT",
        tmp_path,
    )
    monkeypatch.setattr(
        storage_factory.boto3,
        "client",
        boto_client_factory,
    )

    storage_factory.get_storage_provider.cache_clear()
    storage_factory.get_minio_client.cache_clear()

    try:
        first_provider = storage_factory.get_storage_provider()
        second_provider = storage_factory.get_storage_provider()

        assert isinstance(first_provider, LocalStorageProvider)
        assert second_provider is first_provider
        boto_client_factory.assert_not_called()
    finally:
        storage_factory.get_storage_provider.cache_clear()
        storage_factory.get_minio_client.cache_clear()



def test_get_storage_provider_returns_cached_minio_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    minio_client = Mock()
    minio_client.head_object.return_value = {}
    boto_client_factory = Mock(return_value=minio_client)

    monkeypatch.setattr(
        storage_factory.settings,
        "STORAGE_PROVIDER",
        "minio",
    )
    monkeypatch.setattr(
        storage_factory.settings,
        "STORAGE_MINIO_ENDPOINT",
        "http://127.0.0.1:9000",
    )
    monkeypatch.setattr(
        storage_factory.settings,
        "STORAGE_MINIO_ACCESS_KEY",
        "test-app-user",
    )
    monkeypatch.setattr(
        storage_factory.settings,
        "STORAGE_MINIO_SECRET_KEY",
        SecretStr("test-secret-key"),
    )
    monkeypatch.setattr(
        storage_factory.settings,
        "STORAGE_MINIO_BUCKET",
        "test-files",
    )
    monkeypatch.setattr(
        storage_factory.boto3,
        "client",
        boto_client_factory,
    )

    storage_factory.get_storage_provider.cache_clear()
    storage_factory.get_minio_client.cache_clear()

    try:
        first_provider = storage_factory.get_storage_provider()
        second_provider = storage_factory.get_storage_provider()

        assert isinstance(first_provider, MinIOStorageProvider)
        assert second_provider is first_provider
        assert storage_factory.get_minio_client() is minio_client

        assert first_provider.exists("users/42/file-id") is True
        minio_client.head_object.assert_called_once_with(
            Bucket="test-files",
            Key="users/42/file-id",
        )

        boto_client_factory.assert_called_once()
        arguments, keyword_arguments = boto_client_factory.call_args

        assert arguments == ("s3",)
        assert keyword_arguments["endpoint_url"] == "http://127.0.0.1:9000"
        assert keyword_arguments["aws_access_key_id"] == "test-app-user"
        assert keyword_arguments["aws_secret_access_key"] == "test-secret-key"
        assert keyword_arguments["region_name"] == "us-east-1"

        boto_config = keyword_arguments["config"]
        assert boto_config.signature_version == "s3v4"
        assert boto_config.s3 == {"addressing_style": "path"}
    finally:
        storage_factory.get_storage_provider.cache_clear()
        storage_factory.get_minio_client.cache_clear()


