from contextlib import suppress
from hashlib import sha256
from os import getenv
from uuid import uuid4

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.file_resource import FileResource, FileStatus
from app.storage import factory as storage_factory
from app.storage.exceptions import StorageOperationError

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        getenv("RUN_MINIO_INTEGRATION_TESTS") != "1",
        reason="Set RUN_MINIO_INTEGRATION_TESTS=1 to run real MinIO tests.",
    ),
]


def test_minio_file_lifecycle(
    client: TestClient,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        storage_factory.settings,
        "STORAGE_PROVIDER",
        "minio",
    )

    storage_factory.get_storage_provider.cache_clear()
    storage_factory.get_minio_client.cache_clear()

    provider = storage_factory.get_storage_provider()
    minio_client = storage_factory.get_minio_client()
    bucket = storage_factory.settings.STORAGE_MINIO_BUCKET

    assert bucket is not None

    object_key: str | None = None
    content = b"%PDF-1.7\nreal minio file content"
    credentials = {
        "email": f"minio-lifecycle-{uuid4().hex}@example.com",
        "password": "password123",
    }

    try:
        register_response = client.post(
            "/auth/register",
            json=credentials,
        )
        assert register_response.status_code == status.HTTP_201_CREATED

        login_response = client.post(
            "/auth/login",
            json=credentials,
        )
        assert login_response.status_code == status.HTTP_200_OK

        headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}
        upload_response = client.post(
            "/files",
            headers=headers,
            files={
                "upload": (
                    "report.pdf",
                    content,
                    "application/pdf",
                ),
            },
        )

        assert upload_response.status_code == status.HTTP_201_CREATED
        file_id = upload_response.json()["id"]

        resource = session.get(FileResource, file_id)
        assert resource is not None

        object_key = resource.object_key

        assert resource.storage_provider == "minio"
        assert resource.bucket == bucket
        assert resource.status == FileStatus.READY.value
        assert resource.size_bytes == len(content)
        assert resource.sha256 == sha256(content).hexdigest()
        assert provider.exists(object_key) is True

        detail_response = client.get(
            f"/files/{file_id}",
            headers=headers,
        )
        assert detail_response.status_code == status.HTTP_200_OK

        list_response = client.get(
            "/files",
            headers=headers,
        )
        assert list_response.status_code == status.HTTP_200_OK
        assert [item["id"] for item in list_response.json()["items"]] == [file_id]

        download_response = client.get(
            f"/files/{file_id}/download",
            headers=headers,
        )
        assert download_response.status_code == status.HTTP_200_OK
        assert download_response.content == content

        delete_response = client.delete(
            f"/files/{file_id}",
            headers=headers,
        )
        assert delete_response.status_code == status.HTTP_204_NO_CONTENT

        session.expire_all()
        deleted_resource = session.get(FileResource, file_id)

        assert deleted_resource is not None
        assert deleted_resource.status == FileStatus.DELETED.value
        assert deleted_resource.deleted_at is not None
        assert provider.exists(object_key) is False

        missing_response = client.get(
            f"/files/{file_id}",
            headers=headers,
        )
        assert missing_response.status_code == status.HTTP_404_NOT_FOUND

        empty_list_response = client.get(
            "/files",
            headers=headers,
        )
        assert empty_list_response.status_code == status.HTTP_200_OK
        assert empty_list_response.json()["items"] == []
    finally:
        if object_key is not None:
            with suppress(StorageOperationError):
                provider.delete(object_key)

        minio_client.close()
        storage_factory.get_storage_provider.cache_clear()
        storage_factory.get_minio_client.cache_clear()
