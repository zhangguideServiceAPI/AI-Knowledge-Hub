from datetime import datetime
from unittest.mock import Mock
from uuid import uuid4

from fastapi import status
from fastapi.testclient import TestClient
import pytest

from app.api.dependencies import get_file_service
from app.main import app
from app.schemas.file import FileResourceResponse
from app.services.file_service import FileService
from app.storage.exceptions import (
    EmptyFileError,
    FileTooLargeError,
    FileUploadFailedError,
    InvalidFileNameError,
    StorageUnavailableError,
    UnsupportedFileTypeError,
)


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
