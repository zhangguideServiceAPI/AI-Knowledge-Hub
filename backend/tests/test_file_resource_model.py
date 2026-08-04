import pytest
from sqlalchemy.exc import IntegrityError
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.file_resource import FileResource, FileStatus
from app.models.user import User


def _create_user(session: Session, email: str) -> User:
    user = User(
        email=email,
        password_hash="hashed-password",
    )
    session.add(user)
    session.flush()
    return user


def _build_resource(
    owner_id: int,
    object_key: str,
    *,
    sha256: str = "a" * 64,
    size_bytes: int = 1024,
) -> FileResource:
    return FileResource(
        owner_id=owner_id,
        storage_provider="local",
        bucket="local",
        object_key=object_key,
        original_filename="report.pdf",
        content_type="application/pdf",
        size_bytes=size_bytes,
        sha256=sha256,
    )


def test_create_file_resource_with_defaults(session: Session) -> None:
    user = User(
        email="file-owner@example.com",
        password_hash="hashed-password",
    )
    session.add(user)
    session.flush()

    resource = FileResource(
        owner_id=user.id,
        storage_provider="local",
        bucket="local",
        object_key="users/1/report.bin",
        original_filename="report.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        sha256="a" * 64,
    )
    session.add(resource)
    session.flush()
    session.refresh(resource)

    assert UUID(resource.id).version == 4
    assert resource.owner_id == user.id
    assert resource.status == FileStatus.PENDING_UPLOAD.value
    assert resource.failure_reason is None
    assert resource.deleted_at is None
    assert resource.created_at is not None
    assert resource.updated_at is not None


def test_storage_location_must_be_unique(session: Session) -> None:
    user = _create_user(session, "unique-location@example.com")

    session.add(_build_resource(user.id, "users/1/same.bin"))
    session.flush()

    session.add(_build_resource(user.id, "users/1/same.bin"))

    with pytest.raises(IntegrityError):
        session.flush()


def test_sha256_can_be_repeated(session: Session) -> None:
    user = _create_user(session, "same-sha@example.com")
    same_sha256 = "b" * 64

    first = _build_resource(
        user.id,
        "users/1/first.bin",
        sha256=same_sha256,
    )
    second = _build_resource(
        user.id,
        "users/1/second.bin",
        sha256=same_sha256,
    )

    session.add_all([first, second])
    session.flush()

    assert first.id != second.id
    assert first.sha256 == second.sha256


def test_size_bytes_cannot_be_negative(session: Session) -> None:
    user = _create_user(session, "negative-size@example.com")
    resource = _build_resource(
        user.id,
        "users/1/negative.bin",
        size_bytes=-1,
    )
    session.add(resource)

    with pytest.raises(IntegrityError):
        session.flush()


def test_owner_must_exist(session: Session) -> None:
    resource = _build_resource(
        owner_id=999_999,
        object_key="users/missing-owner/file.bin",
    )
    session.add(resource)

    with pytest.raises(IntegrityError):
        session.flush()
