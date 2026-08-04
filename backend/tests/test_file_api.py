from datetime import datetime
from io import BytesIO
from unittest.mock import Mock
from uuid import uuid4

from fastapi import status
from fastapi.testclient import TestClient
import pytest

from app.api.dependencies import get_file_service
from app.api.dependencies import get_storage_provider
from app.main import app
from app.schemas.file import FileResourceListResponse, FileResourceResponse
from app.services.file_service import FileDownload, FileService
from app.storage.exceptions import (
    EmptyFileError,
    FileContentUnavailableError,
    FileDeleteFailedError,
    FileResourceNotFoundError,
    FileTooLargeError,
    FileUploadFailedError,
    InvalidFileNameError,
    StorageUnavailableError,
    UnsupportedFileTypeError,
)
from app.storage.local import LocalStorageProvider


class TrackingBytesIO(BytesIO):
    def __init__(self, content: bytes) -> None:
        super().__init__(content)
        self.read_sizes: list[int] = []

    def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        return super().read(size)


def test_upload_file_returns_created_resource(
    client: TestClient,
) -> None:
    response_model = FileResourceResponse(
        id=uuid4(),
        original_filename="report.pdf",
        content_type="application/pdf",
        size_bytes=5,
        status="ready",
        created_at=datetime(2026, 8, 4, 10, 0),
        updated_at=datetime(2026, 8, 4, 10, 0),
    )

    file_service = Mock(spec=FileService)
    captured_upload: dict[str, object] = {}

    def capture_upload(**kwargs: object) -> FileResourceResponse:
        captured_upload.update(kwargs)
        source = kwargs["source"]
        assert hasattr(source, "read")
        captured_upload["content"] = source.read()
        return response_model

    file_service.upload.side_effect = capture_upload

    app.dependency_overrides[get_file_service] = lambda: file_service

    try:
        register_response = client.post(
            "/auth/register",
            json={
                "email": "file-api@example.com",
                "password": "password123",
            },
        )
        assert register_response.status_code == status.HTTP_201_CREATED

        login_response = client.post(
            "/auth/login",
            json={
                "email": "file-api@example.com",
                "password": "password123",
            },
        )
        token = login_response.json()["access_token"]

        response = client.post(
            "/files",
            headers={"Authorization": f"Bearer {token}"},
            files={
                "upload": (
                    "report.pdf",
                    b"%PDF-",
                    "application/pdf",
                ),
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["original_filename"] == "report.pdf"
        file_service.upload.assert_called_once()

        assert captured_upload["owner_id"] == register_response.json()["id"]
        assert captured_upload["original_filename"] == "report.pdf"
        assert captured_upload["content_type"] == "application/pdf"
        assert captured_upload["content"] == b"%PDF-"
    finally:
        app.dependency_overrides.pop(get_file_service, None)


def test_upload_file_requires_access_token(
    client: TestClient,
) -> None:
    response = client.post(
        "/files",
        files={
            "upload": (
                "report.pdf",
                b"%PDF-",
                "application/pdf",
            ),
        },
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {
        "detail": "Invalid or missing access token.",
    }


@pytest.mark.parametrize(
    ("service_error", "expected_status", "expected_detail"),
    [
        (
            InvalidFileNameError(),
            status.HTTP_400_BAD_REQUEST,
            "Invalid upload metadata.",
        ),
        (
            EmptyFileError(),
            status.HTTP_400_BAD_REQUEST,
            "Invalid upload metadata.",
        ),
        (
            FileTooLargeError(),
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            "Uploaded file is too large.",
        ),
        (
            UnsupportedFileTypeError(),
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Unsupported file type.",
        ),
        (
            StorageUnavailableError(),
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "File storage is temporarily unavailable.",
        ),
        (
            FileUploadFailedError(),
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "File upload failed.",
        ),
    ],
)
def test_upload_file_maps_service_errors(
    client: TestClient,
    service_error: Exception,
    expected_status: int,
    expected_detail: str,
) -> None:
    credentials = {
        "email": "file-error@example.com",
        "password": "password123",
    }
    client.post("/auth/register", json=credentials)
    login_response = client.post("/auth/login", json=credentials)

    file_service = Mock(spec=FileService)
    file_service.upload.side_effect = service_error
    app.dependency_overrides[get_file_service] = lambda: file_service

    try:
        response = client.post(
            "/files",
            headers={
                "Authorization": f"Bearer {login_response.json()['access_token']}"
            },
            files={
                "upload": (
                    "report.pdf",
                    b"%PDF-",
                    "application/pdf",
                ),
            },
        )
    finally:
        app.dependency_overrides.pop(get_file_service, None)

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}


def test_get_file_returns_resource(
    client: TestClient,
) -> None:
    credentials = {
        "email": "file-detail-api@example.com",
        "password": "password123",
    }
    register_response = client.post(
        "/auth/register",
        json=credentials,
    )
    login_response = client.post(
        "/auth/login",
        json=credentials,
    )

    file_id = uuid4()
    response_model = FileResourceResponse(
        id=file_id,
        original_filename="report.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        status="ready",
        created_at=datetime(2026, 8, 4, 10, 0),
        updated_at=datetime(2026, 8, 4, 10, 0),
    )

    file_service = Mock(spec=FileService)
    file_service.get_file.return_value = response_model
    app.dependency_overrides[get_file_service] = lambda: file_service

    try:
        response = client.get(
            f"/files/{file_id}",
            headers={
                "Authorization": (f"Bearer {login_response.json()['access_token']}")
            },
        )
    finally:
        app.dependency_overrides.pop(get_file_service, None)

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["id"] == str(file_id)
    assert response.json()["original_filename"] == "report.pdf"

    file_service.get_file.assert_called_once_with(
        owner_id=register_response.json()["id"],
        file_id=str(file_id),
    )


def test_get_file_returns_not_found(
    client: TestClient,
) -> None:
    credentials = {
        "email": "missing-file-api@example.com",
        "password": "password123",
    }
    client.post("/auth/register", json=credentials)
    login_response = client.post("/auth/login", json=credentials)

    file_service = Mock(spec=FileService)
    file_service.get_file.side_effect = FileResourceNotFoundError()
    app.dependency_overrides[get_file_service] = lambda: file_service

    try:
        response = client.get(
            "/files/missing-file-id",
            headers={
                "Authorization": (f"Bearer {login_response.json()['access_token']}")
            },
        )
    finally:
        app.dependency_overrides.pop(get_file_service, None)

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {
        "detail": "File not found.",
    }


def test_list_files_uses_default_pagination(
    client: TestClient,
) -> None:
    credentials = {
        "email": "file-list-default@example.com",
        "password": "password123",
    }
    register_response = client.post("/auth/register", json=credentials)
    login_response = client.post("/auth/login", json=credentials)

    file_service = Mock(spec=FileService)
    file_service.list_files.return_value = FileResourceListResponse(
        items=[],
        limit=20,
        offset=0,
    )
    app.dependency_overrides[get_file_service] = lambda: file_service

    try:
        response = client.get(
            "/files",
            headers={
                "Authorization": f"Bearer {login_response.json()['access_token']}"
            },
        )
    finally:
        app.dependency_overrides.pop(get_file_service, None)

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "items": [],
        "limit": 20,
        "offset": 0,
    }
    file_service.list_files.assert_called_once_with(
        owner_id=register_response.json()["id"],
        limit=20,
        offset=0,
    )


def test_list_files_accepts_custom_pagination(
    client: TestClient,
) -> None:
    credentials = {
        "email": "file-list-custom@example.com",
        "password": "password123",
    }
    register_response = client.post("/auth/register", json=credentials)
    login_response = client.post("/auth/login", json=credentials)

    file_service = Mock(spec=FileService)
    file_service.list_files.return_value = FileResourceListResponse(
        items=[],
        limit=5,
        offset=10,
    )
    app.dependency_overrides[get_file_service] = lambda: file_service

    try:
        response = client.get(
            "/files?limit=5&offset=10",
            headers={
                "Authorization": f"Bearer {login_response.json()['access_token']}"
            },
        )
    finally:
        app.dependency_overrides.pop(get_file_service, None)

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["limit"] == 5
    assert response.json()["offset"] == 10
    file_service.list_files.assert_called_once_with(
        owner_id=register_response.json()["id"],
        limit=5,
        offset=10,
    )


@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=101",
        "offset=-1",
    ],
)
def test_list_files_rejects_invalid_pagination(
    client: TestClient,
    query: str,
) -> None:
    credentials = {
        "email": "file-list-invalid@example.com",
        "password": "password123",
    }
    client.post("/auth/register", json=credentials)
    login_response = client.post("/auth/login", json=credentials)

    file_service = Mock(spec=FileService)
    app.dependency_overrides[get_file_service] = lambda: file_service

    try:
        response = client.get(
            f"/files?{query}",
            headers={
                "Authorization": f"Bearer {login_response.json()['access_token']}"
            },
        )
    finally:
        app.dependency_overrides.pop(get_file_service, None)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    file_service.list_files.assert_not_called()


def test_download_file_streams_content_and_closes_stream(
    client: TestClient,
) -> None:
    credentials = {
        "email": "file-download-api@example.com",
        "password": "password123",
    }
    register_response = client.post("/auth/register", json=credentials)
    login_response = client.post("/auth/login", json=credentials)

    file_id = uuid4()
    stream = TrackingBytesIO(b"abcdefgh")
    file_service = Mock(spec=FileService)
    file_service.download_file.return_value = FileDownload(
        stream=stream,
        original_filename="study report.pdf",
        content_type="application/pdf",
        size_bytes=8,
        chunk_size=3,
    )
    app.dependency_overrides[get_file_service] = lambda: file_service

    try:
        response = client.get(
            f"/files/{file_id}/download",
            headers={
                "Authorization": f"Bearer {login_response.json()['access_token']}"
            },
        )
    finally:
        app.dependency_overrides.pop(get_file_service, None)

    assert response.status_code == status.HTTP_200_OK
    assert response.content == b"abcdefgh"
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-length"] == "8"
    assert response.headers["content-disposition"] == (
        "attachment; filename*=UTF-8''study%20report.pdf"
    )
    assert stream.read_sizes == [3, 3, 3, 3]
    assert stream.closed is True
    file_service.download_file.assert_called_once_with(
        owner_id=register_response.json()["id"],
        file_id=str(file_id),
    )


@pytest.mark.parametrize(
    ("service_error", "expected_status", "expected_detail"),
    [
        (
            FileResourceNotFoundError(),
            status.HTTP_404_NOT_FOUND,
            "File not found.",
        ),
        (
            FileContentUnavailableError(),
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "File content is unavailable.",
        ),
        (
            StorageUnavailableError(),
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "File storage is temporarily unavailable.",
        ),
    ],
)
def test_download_file_maps_service_errors(
    client: TestClient,
    service_error: Exception,
    expected_status: int,
    expected_detail: str,
) -> None:
    credentials = {
        "email": "file-download-error@example.com",
        "password": "password123",
    }
    client.post("/auth/register", json=credentials)
    login_response = client.post("/auth/login", json=credentials)

    file_service = Mock(spec=FileService)
    file_service.download_file.side_effect = service_error
    app.dependency_overrides[get_file_service] = lambda: file_service

    try:
        response = client.get(
            "/files/download-error/download",
            headers={
                "Authorization": f"Bearer {login_response.json()['access_token']}"
            },
        )
    finally:
        app.dependency_overrides.pop(get_file_service, None)

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}


def test_delete_file_returns_no_content(
    client: TestClient,
) -> None:
    credentials = {
        "email": "file-delete-api@example.com",
        "password": "password123",
    }
    register_response = client.post("/auth/register", json=credentials)
    login_response = client.post("/auth/login", json=credentials)

    file_id = uuid4()
    file_service = Mock(spec=FileService)
    app.dependency_overrides[get_file_service] = lambda: file_service

    try:
        response = client.delete(
            f"/files/{file_id}",
            headers={
                "Authorization": f"Bearer {login_response.json()['access_token']}"
            },
        )
    finally:
        app.dependency_overrides.pop(get_file_service, None)

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert response.content == b""
    file_service.delete_file.assert_called_once_with(
        owner_id=register_response.json()["id"],
        file_id=str(file_id),
    )


@pytest.mark.parametrize(
    ("service_error", "expected_status", "expected_detail"),
    [
        (
            FileResourceNotFoundError(),
            status.HTTP_404_NOT_FOUND,
            "File not found.",
        ),
        (
            FileDeleteFailedError(),
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "File deletion failed.",
        ),
        (
            StorageUnavailableError(),
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "File storage is temporarily unavailable.",
        ),
    ],
)
def test_delete_file_maps_service_errors(
    client: TestClient,
    service_error: Exception,
    expected_status: int,
    expected_detail: str,
) -> None:
    credentials = {
        "email": "file-delete-error@example.com",
        "password": "password123",
    }
    client.post("/auth/register", json=credentials)
    login_response = client.post("/auth/login", json=credentials)

    file_service = Mock(spec=FileService)
    file_service.delete_file.side_effect = service_error
    app.dependency_overrides[get_file_service] = lambda: file_service

    try:
        response = client.delete(
            "/files/delete-error",
            headers={
                "Authorization": f"Bearer {login_response.json()['access_token']}"
            },
        )
    finally:
        app.dependency_overrides.pop(get_file_service, None)

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}


def test_local_file_lifecycle(
    client: TestClient,
    tmp_path,
) -> None:
    credentials = {
        "email": "local-file-lifecycle@example.com",
        "password": "password123",
    }
    client.post("/auth/register", json=credentials)
    login_response = client.post("/auth/login", json=credentials)
    headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

    storage_provider = LocalStorageProvider(
        root=tmp_path,
        chunk_size=4,
    )
    app.dependency_overrides[get_storage_provider] = lambda: storage_provider

    try:
        upload_response = client.post(
            "/files",
            headers=headers,
            files={
                "upload": (
                    "report.pdf",
                    b"%PDF-1.7\nlocal file content",
                    "application/pdf",
                ),
            },
        )
        assert upload_response.status_code == status.HTTP_201_CREATED
        file_id = upload_response.json()["id"]

        detail_response = client.get(
            f"/files/{file_id}",
            headers=headers,
        )
        assert detail_response.status_code == status.HTTP_200_OK

        list_response = client.get("/files", headers=headers)
        assert list_response.status_code == status.HTTP_200_OK
        assert [item["id"] for item in list_response.json()["items"]] == [file_id]

        download_response = client.get(
            f"/files/{file_id}/download",
            headers=headers,
        )
        assert download_response.status_code == status.HTTP_200_OK
        assert download_response.content == b"%PDF-1.7\nlocal file content"

        delete_response = client.delete(
            f"/files/{file_id}",
            headers=headers,
        )
        assert delete_response.status_code == status.HTTP_204_NO_CONTENT

        missing_response = client.get(
            f"/files/{file_id}",
            headers=headers,
        )
        assert missing_response.status_code == status.HTTP_404_NOT_FOUND

        empty_list_response = client.get("/files", headers=headers)
        assert empty_list_response.status_code == status.HTTP_200_OK
        assert empty_list_response.json()["items"] == []
    finally:
        app.dependency_overrides.pop(get_storage_provider, None)
