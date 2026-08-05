from functools import lru_cache

import boto3
from botocore.client import BaseClient
from botocore.config import Config

from app.core.config import settings
from app.storage.local import LocalStorageProvider
from app.storage.minio import MinIOStorageProvider
from app.storage.provider import StorageProvider

MINIO_READINESS_TIMEOUT_SECONDS = 1.0


def get_storage_bucket() -> str:
    if settings.STORAGE_PROVIDER == "local":
        return "local"

    bucket = settings.STORAGE_MINIO_BUCKET
    if bucket is None:
        raise RuntimeError("MinIO bucket configuration is missing.")

    return bucket


def _create_minio_client(config: Config) -> BaseClient:
    endpoint = settings.STORAGE_MINIO_ENDPOINT
    access_key = settings.STORAGE_MINIO_ACCESS_KEY
    secret_key = settings.STORAGE_MINIO_SECRET_KEY

    if endpoint is None or access_key is None or secret_key is None:
        raise RuntimeError("MinIO client configuration is incomplete.")

    return boto3.client(
        "s3",
        endpoint_url=str(endpoint),
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key.get_secret_value(),
        region_name="us-east-1",
        config=config,
    )


@lru_cache(maxsize=1)
def get_minio_client() -> BaseClient:
    return _create_minio_client(
        Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
        )
    )


@lru_cache(maxsize=1)
def get_minio_readiness_client() -> BaseClient:
    return _create_minio_client(
        Config(
            signature_version="s3v4",
            connect_timeout=MINIO_READINESS_TIMEOUT_SECONDS,
            read_timeout=MINIO_READINESS_TIMEOUT_SECONDS,
            retries={
                "mode": "standard",
                "total_max_attempts": 1,
            },
            s3={"addressing_style": "path"},
        )
    )


@lru_cache(maxsize=1)
def get_storage_provider() -> StorageProvider:
    if settings.STORAGE_PROVIDER == "local":
        return LocalStorageProvider(
            root=settings.STORAGE_LOCAL_ROOT,
            chunk_size=settings.UPLOAD_CHUNK_SIZE_BYTES,
        )

    return MinIOStorageProvider(
        client=get_minio_client(),
        bucket=get_storage_bucket(),
    )
