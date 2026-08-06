from io import BytesIO
import logging
from unittest.mock import Mock

import pytest

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.file_resource import FileResource, FileStatus
from app.models.user import User
from app.services.file_service import FileService
from app.storage.exceptions import (
    FileUploadFailedError,
    StorageOperationError,
    StorageUnavailableError,
    UnsupportedFileTypeError,
)
from app.storage.provider import StorageProvider


def test_upload_creates_ready_resource(
    session: Session,
) -> None:
    user = User(
        email="upload-owner@example.com",
        password_hash="hashed-password",
    )
    session.add(user)
    session.flush()

    storage_provider = Mock(spec=StorageProvider)
    service = FileService(
        session,
        storage_provider,
        bucket="local",
        max_upload_size=1024 * 1024,
        chunk_size=4,
    )

    result = service.upload(
        owner_id=user.id,
        original_filename="report.pdf",
        content_type="application/pdf",
        source=BytesIO(b"%PDF-1.7\nfile content"),
    )

    assert result.status == FileStatus.READY
    assert result.original_filename == "report.pdf"
    assert result.size_bytes == len(b"%PDF-1.7\nfile content")

    stored_resource = session.get(
        FileResource,
        str(result.id),
    )

    assert stored_resource is not None
    assert stored_resource.status == FileStatus.READY.value
    assert stored_resource.owner_id == user.id
    assert stored_resource.object_key.startswith(f"users/{user.id}/")
    assert "report.pdf" not in stored_resource.object_key

    storage_provider.put.assert_called_once()
    put_object_key, put_source = storage_provider.put.call_args.args

    assert put_object_key == stored_resource.object_key
    assert put_source.tell() == 0


def test_upload_marks_failed_when_provider_write_fails(
    session: Session,
) -> None:
    user = User(
        email="provider-failure@example.com",
        password_hash="hashed-password",
    )
    session.add(user)
    session.flush()

    storage_provider = Mock(spec=StorageProvider)
    storage_provider.put.side_effect = StorageOperationError()

    service = FileService(
        session,
        storage_provider,
        bucket="local",
        max_upload_size=1024 * 1024,
        chunk_size=4,
    )

    with pytest.raises(StorageUnavailableError):
        service.upload(
            owner_id=user.id,
            original_filename="report.pdf",
            content_type="application/pdf",
            source=BytesIO(b"%PDF-1.7\nfile content"),
        )

    resource = session.query(FileResource).one()

    assert resource.status == FileStatus.UPLOAD_FAILED.value
    assert resource.failure_reason == "provider_write_failed"


def test_upload_rejection_logs_fixed_reason(
    session: Session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    user = User(
        email="validation-log@example.com",
        password_hash="hashed-password",
    )
    session.add(user)
    session.flush()

    service = FileService(
        session,
        Mock(spec=StorageProvider),
        bucket="local",
        max_upload_size=1024 * 1024,
        chunk_size=4,
    )

    with caplog.at_level(logging.WARNING, logger="ai_knowledge_hub"):
        with pytest.raises(UnsupportedFileTypeError):
            service.upload(
                owner_id=user.id,
                original_filename="report.pdf",
                content_type="application/pdf",
                source=BytesIO(b"not-pdf"),
            )

    assert "storage.upload.rejected" in caplog.text
    assert "user_id=" in caplog.text
    assert "not-pdf" not in caplog.text
    assert "report.pdf" not in caplog.text


def test_upload_deletes_object_when_ready_commit_fails(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = User(
        email="commit-failure@example.com",
        password_hash="hashed-password",
    )
    session.add(user)
    session.flush()

    storage_provider = Mock(spec=StorageProvider)
    service = FileService(
        session,
        storage_provider,
        bucket="local",
        max_upload_size=1024 * 1024,
        chunk_size=4,
    )

    original_commit = session.commit
    commit_count = 0

    def commit_with_failure() -> None:
        nonlocal commit_count
        commit_count += 1

        if commit_count == 2:
            raise SQLAlchemyError("ready commit failed")

        original_commit()

    monkeypatch.setattr(session, "commit", commit_with_failure)

    with pytest.raises(FileUploadFailedError):
        service.upload(
            owner_id=user.id,
            original_filename="report.pdf",
            content_type="application/pdf",
            source=BytesIO(b"%PDF-1.7\nfile content"),
        )

    resource = session.query(FileResource).one()

    assert resource.status == FileStatus.UPLOAD_FAILED.value
    assert resource.failure_reason == "metadata_commit_failed"
    storage_provider.delete.assert_called_once_with(resource.object_key)


def test_upload_marks_cleanup_required_when_compensation_fails(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = User(
        email="cleanup-failure@example.com",
        password_hash="hashed-password",
    )
    session.add(user)
    session.flush()

    storage_provider = Mock(spec=StorageProvider)
    storage_provider.delete.side_effect = StorageOperationError()

    service = FileService(
        session,
        storage_provider,
        bucket="local",
        max_upload_size=1024 * 1024,
        chunk_size=4,
    )

    original_commit = session.commit
    commit_count = 0

    def commit_with_failure() -> None:
        nonlocal commit_count
        commit_count += 1

        if commit_count == 2:
            raise SQLAlchemyError("ready commit failed")

        original_commit()

    monkeypatch.setattr(session, "commit", commit_with_failure)

    with pytest.raises(FileUploadFailedError):
        service.upload(
            owner_id=user.id,
            original_filename="report.pdf",
            content_type="application/pdf",
            source=BytesIO(b"%PDF-1.7\nfile content"),
        )

    resource = session.query(FileResource).one()

    assert resource.status == FileStatus.CLEANUP_REQUIRED.value
    assert resource.failure_reason == "cleanup_failed"
    storage_provider.delete.assert_called_once_with(resource.object_key)
