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
    FileContentUnavailableError,
    FileDeleteFailedError,
    FileResourceNotFoundError,
    FileUploadFailedError,
    StorageObjectNotFoundError,
    StorageOperationError,
    StorageUnavailableError,
    UnsupportedFileTypeError,
)
from app.storage.provider import StorageProvider


def _create_ready_file(
    session: Session,
    *,
    owner_id: int,
    object_key: str,
) -> FileResource:
    resource = FileResource(
        owner_id=owner_id,
        storage_provider="local",
        bucket="local",
        object_key=object_key,
        original_filename="report.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        sha256="a" * 64,
        status=FileStatus.READY.value,
    )
    session.add(resource)
    session.flush()
    session.refresh(resource)
    return resource


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


def test_get_file_returns_owned_ready_resource(
    session: Session,
) -> None:
    user = User(
        email="file-detail@example.com",
        password_hash="hashed-password",
    )
    session.add(user)
    session.flush()

    resource = _create_ready_file(
        session,
        owner_id=user.id,
        object_key=f"users/{user.id}/owned-file",
    )

    service = FileService(
        session,
        Mock(spec=StorageProvider),
        bucket="local",
        max_upload_size=1024,
        chunk_size=4,
    )

    result = service.get_file(
        owner_id=user.id,
        file_id=resource.id,
    )

    assert str(result.id) == resource.id
    assert result.original_filename == "report.pdf"
    assert result.status == FileStatus.READY


def test_get_file_rejects_missing_resource(
    session: Session,
) -> None:
    user = User(
        email="missing-file@example.com",
        password_hash="hashed-password",
    )
    session.add(user)
    session.flush()

    service = FileService(
        session,
        Mock(spec=StorageProvider),
        bucket="local",
        max_upload_size=1024,
        chunk_size=4,
    )

    with pytest.raises(FileResourceNotFoundError):
        service.get_file(
            owner_id=user.id,
            file_id="missing-file-id",
        )


def test_get_file_hides_other_users_resource(
    session: Session,
) -> None:
    owner = User(
        email="owner@example.com",
        password_hash="hashed-password",
    )
    other_user = User(
        email="other-user@example.com",
        password_hash="hashed-password",
    )
    session.add_all([owner, other_user])
    session.flush()

    resource = _create_ready_file(
        session,
        owner_id=owner.id,
        object_key=f"users/{owner.id}/private-file",
    )

    service = FileService(
        session,
        Mock(spec=StorageProvider),
        bucket="local",
        max_upload_size=1024,
        chunk_size=4,
    )

    with pytest.raises(FileResourceNotFoundError):
        service.get_file(
            owner_id=other_user.id,
            file_id=resource.id,
        )


def test_list_files_returns_only_owned_resources(
    session: Session,
) -> None:
    owner = User(
        email="list-owner@example.com",
        password_hash="hashed-password",
    )
    other_user = User(
        email="list-other@example.com",
        password_hash="hashed-password",
    )
    session.add_all([owner, other_user])
    session.flush()

    owner_resource = _create_ready_file(
        session,
        owner_id=owner.id,
        object_key=f"users/{owner.id}/owned-file",
    )
    _create_ready_file(
        session,
        owner_id=other_user.id,
        object_key=f"users/{other_user.id}/private-file",
    )

    service = FileService(
        session,
        Mock(spec=StorageProvider),
        bucket="local",
        max_upload_size=1024,
        chunk_size=4,
    )

    result = service.list_files(
        owner_id=owner.id,
        limit=20,
        offset=0,
    )

    assert len(result.items) == 1
    assert str(result.items[0].id) == owner_resource.id
    assert result.items[0].original_filename == "report.pdf"


def test_list_files_applies_pagination(
    session: Session,
) -> None:
    user = User(
        email="list-pagination@example.com",
        password_hash="hashed-password",
    )
    session.add(user)
    session.flush()

    _create_ready_file(
        session,
        owner_id=user.id,
        object_key=f"users/{user.id}/first-file",
    )
    _create_ready_file(
        session,
        owner_id=user.id,
        object_key=f"users/{user.id}/second-file",
    )

    service = FileService(
        session,
        Mock(spec=StorageProvider),
        bucket="local",
        max_upload_size=1024,
        chunk_size=4,
    )

    result = service.list_files(
        owner_id=user.id,
        limit=1,
        offset=1,
    )

    assert len(result.items) == 1
    assert result.limit == 1
    assert result.offset == 1


def test_delete_file_hides_resource_before_deleting_object(
    session: Session,
) -> None:
    user = User(
        email="delete-success@example.com",
        password_hash="hashed-password",
    )
    session.add(user)
    session.flush()
    resource = _create_ready_file(
        session,
        owner_id=user.id,
        object_key=f"users/{user.id}/delete-success",
    )

    storage_provider = Mock(spec=StorageProvider)

    def assert_deleting_before_provider_call(object_key: str) -> None:
        session.expire_all()
        persisted = session.get(FileResource, resource.id)
        assert persisted is not None
        assert persisted.status == FileStatus.DELETING.value
        assert object_key == resource.object_key

    storage_provider.delete.side_effect = assert_deleting_before_provider_call
    service = FileService(
        session,
        storage_provider,
        bucket="local",
        max_upload_size=1024,
        chunk_size=4,
    )

    service.delete_file(
        owner_id=user.id,
        file_id=resource.id,
    )

    session.expire_all()
    persisted = session.get(FileResource, resource.id)
    assert persisted is not None
    assert persisted.status == FileStatus.DELETED.value
    assert persisted.deleted_at is not None
    storage_provider.delete.assert_called_once_with(resource.object_key)


def test_delete_file_marks_cleanup_required_when_provider_fails(
    session: Session,
) -> None:
    user = User(
        email="delete-provider-failure@example.com",
        password_hash="hashed-password",
    )
    session.add(user)
    session.flush()
    resource = _create_ready_file(
        session,
        owner_id=user.id,
        object_key=f"users/{user.id}/delete-provider-failure",
    )

    storage_provider = Mock(spec=StorageProvider)
    storage_provider.delete.side_effect = StorageOperationError()
    service = FileService(
        session,
        storage_provider,
        bucket="local",
        max_upload_size=1024,
        chunk_size=4,
    )

    with pytest.raises(StorageUnavailableError):
        service.delete_file(
            owner_id=user.id,
            file_id=resource.id,
        )

    session.expire_all()
    persisted = session.get(FileResource, resource.id)
    assert persisted is not None
    assert persisted.status == FileStatus.CLEANUP_REQUIRED.value
    assert persisted.failure_reason == "provider_delete_failed"


def test_delete_file_does_not_call_provider_when_deleting_commit_fails(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = User(
        email="delete-commit-failure@example.com",
        password_hash="hashed-password",
    )
    session.add(user)
    session.flush()
    resource = _create_ready_file(
        session,
        owner_id=user.id,
        object_key=f"users/{user.id}/delete-commit-failure",
    )

    storage_provider = Mock(spec=StorageProvider)
    monkeypatch.setattr(
        session,
        "commit",
        Mock(side_effect=SQLAlchemyError("deleting commit failed")),
    )
    service = FileService(
        session,
        storage_provider,
        bucket="local",
        max_upload_size=1024,
        chunk_size=4,
    )

    with pytest.raises(FileDeleteFailedError):
        service.delete_file(
            owner_id=user.id,
            file_id=resource.id,
        )

    storage_provider.delete.assert_not_called()


def test_delete_file_marks_cleanup_required_when_final_commit_fails(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = User(
        email="delete-final-commit-failure@example.com",
        password_hash="hashed-password",
    )
    session.add(user)
    session.flush()
    resource = _create_ready_file(
        session,
        owner_id=user.id,
        object_key=f"users/{user.id}/delete-final-commit-failure",
    )

    original_commit = session.commit
    commit_count = 0

    def fail_final_commit() -> None:
        nonlocal commit_count
        commit_count += 1
        if commit_count == 2:
            raise SQLAlchemyError("deleted commit failed")
        original_commit()

    monkeypatch.setattr(session, "commit", fail_final_commit)
    storage_provider = Mock(spec=StorageProvider)
    service = FileService(
        session,
        storage_provider,
        bucket="local",
        max_upload_size=1024,
        chunk_size=4,
    )

    with pytest.raises(FileDeleteFailedError):
        service.delete_file(
            owner_id=user.id,
            file_id=resource.id,
        )

    session.expire_all()
    persisted = session.get(FileResource, resource.id)
    assert persisted is not None
    assert persisted.status == FileStatus.CLEANUP_REQUIRED.value
    assert persisted.failure_reason == "metadata_delete_commit_failed"
    storage_provider.delete.assert_called_once_with(resource.object_key)


def test_download_file_returns_stream_and_safe_metadata(
    session: Session,
) -> None:
    user = User(
        email="download-success@example.com",
        password_hash="hashed-password",
    )
    session.add(user)
    session.flush()
    resource = _create_ready_file(
        session,
        owner_id=user.id,
        object_key=f"users/{user.id}/download-success",
    )

    stream = BytesIO(b"file-content")
    storage_provider = Mock(spec=StorageProvider)
    storage_provider.open.return_value = stream
    service = FileService(
        session,
        storage_provider,
        bucket="local",
        max_upload_size=1024,
        chunk_size=4,
    )

    result = service.download_file(
        owner_id=user.id,
        file_id=resource.id,
    )

    assert result.stream is stream
    assert result.original_filename == "report.pdf"
    assert result.content_type == "application/pdf"
    assert result.size_bytes == 1024
    assert result.chunk_size == 4
    storage_provider.open.assert_called_once_with(resource.object_key)


def test_download_file_marks_cleanup_required_when_object_is_missing(
    session: Session,
) -> None:
    user = User(
        email="download-missing-object@example.com",
        password_hash="hashed-password",
    )
    session.add(user)
    session.flush()
    resource = _create_ready_file(
        session,
        owner_id=user.id,
        object_key=f"users/{user.id}/missing-object",
    )

    storage_provider = Mock(spec=StorageProvider)
    storage_provider.open.side_effect = StorageObjectNotFoundError()
    service = FileService(
        session,
        storage_provider,
        bucket="local",
        max_upload_size=1024,
        chunk_size=4,
    )

    with pytest.raises(FileContentUnavailableError):
        service.download_file(
            owner_id=user.id,
            file_id=resource.id,
        )

    session.expire_all()
    persisted = session.get(FileResource, resource.id)
    assert persisted is not None
    assert persisted.status == FileStatus.CLEANUP_REQUIRED.value
    assert persisted.failure_reason == "storage_object_missing"


def test_download_file_maps_provider_failure(
    session: Session,
) -> None:
    user = User(
        email="download-provider-failure@example.com",
        password_hash="hashed-password",
    )
    session.add(user)
    session.flush()
    resource = _create_ready_file(
        session,
        owner_id=user.id,
        object_key=f"users/{user.id}/download-provider-failure",
    )

    storage_provider = Mock(spec=StorageProvider)
    storage_provider.open.side_effect = StorageOperationError()
    service = FileService(
        session,
        storage_provider,
        bucket="local",
        max_upload_size=1024,
        chunk_size=4,
    )

    with pytest.raises(StorageUnavailableError):
        service.download_file(
            owner_id=user.id,
            file_id=resource.id,
        )


@pytest.mark.parametrize(
    "operation",
    [
        "download",
        "delete",
    ],
)
def test_file_operations_hide_other_users_resource(
    session: Session,
    operation: str,
) -> None:
    owner = User(
        email=f"{operation}-owner@example.com",
        password_hash="hashed-password",
    )
    other_user = User(
        email=f"{operation}-other@example.com",
        password_hash="hashed-password",
    )
    session.add_all([owner, other_user])
    session.flush()
    resource = _create_ready_file(
        session,
        owner_id=owner.id,
        object_key=f"users/{owner.id}/{operation}-private",
    )

    storage_provider = Mock(spec=StorageProvider)
    service = FileService(
        session,
        storage_provider,
        bucket="local",
        max_upload_size=1024,
        chunk_size=4,
    )

    with pytest.raises(FileResourceNotFoundError):
        if operation == "download":
            service.download_file(
                owner_id=other_user.id,
                file_id=resource.id,
            )
        else:
            service.delete_file(
                owner_id=other_user.id,
                file_id=resource.id,
            )

    storage_provider.open.assert_not_called()
    storage_provider.delete.assert_not_called()


def test_delete_file_returns_not_found_when_repeated(
    session: Session,
) -> None:
    user = User(
        email="delete-repeat@example.com",
        password_hash="hashed-password",
    )
    session.add(user)
    session.flush()
    resource = _create_ready_file(
        session,
        owner_id=user.id,
        object_key=f"users/{user.id}/delete-repeat",
    )

    storage_provider = Mock(spec=StorageProvider)
    service = FileService(
        session,
        storage_provider,
        bucket="local",
        max_upload_size=1024,
        chunk_size=4,
    )

    service.delete_file(owner_id=user.id, file_id=resource.id)

    with pytest.raises(FileResourceNotFoundError):
        service.delete_file(owner_id=user.id, file_id=resource.id)

    storage_provider.delete.assert_called_once_with(resource.object_key)
