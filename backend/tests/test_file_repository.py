from datetime import datetime

from sqlalchemy.orm import Session

from app.db.repositories.file_repository import FileRepository
from app.models.file_resource import FileResource, FileStatus
from app.models.user import User


def _create_user(
    session: Session,
    email: str,
) -> User:
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
    status: FileStatus = FileStatus.PENDING_UPLOAD,
    deleted_at: datetime | None = None,
) -> FileResource:
    return FileResource(
        owner_id=owner_id,
        storage_provider="local",
        bucket="local",
        object_key=object_key,
        original_filename="report.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        sha256="a" * 64,
        status=status.value,
        deleted_at=deleted_at,
    )


def test_create_can_be_rolled_back(session: Session) -> None:
    repository = FileRepository(session)
    user = _create_user(session, "rollback-file@example.com")
    resource = repository.create(_build_resource(user.id, "users/1/rollback.bin"))
    file_id = resource.id

    session.rollback()

    assert session.get(FileResource, file_id) is None


def test_get_owned_only_returns_visible_owner_resource(
    session: Session,
) -> None:
    repository = FileRepository(session)
    owner = _create_user(session, "owner@example.com")
    other_user = _create_user(session, "other@example.com")

    ready = repository.create(
        _build_resource(
            owner.id,
            "users/1/ready.bin",
            status=FileStatus.READY,
        )
    )
    pending = repository.create(
        _build_resource(
            owner.id,
            "users/1/pending.bin",
        )
    )
    logically_deleted = repository.create(
        _build_resource(
            owner.id,
            "users/1/deleted.bin",
            status=FileStatus.READY,
            deleted_at=datetime.now(),
        )
    )

    assert repository.get_owned(ready.id, owner.id) == ready
    assert repository.get_owned(ready.id, other_user.id) is None
    assert repository.get_owned(pending.id, owner.id) is None
    assert repository.get_owned(logically_deleted.id, owner.id) is None


def test_list_owned_filters_sorts_and_paginates(
    session: Session,
) -> None:
    repository = FileRepository(session)
    owner = _create_user(session, "list-owner@example.com")
    other_user = _create_user(session, "list-other@example.com")

    oldest = _build_resource(
        owner.id,
        "users/1/oldest.bin",
        status=FileStatus.READY,
    )
    oldest.created_at = datetime(2026, 8, 4, 10, 0)

    middle = _build_resource(
        owner.id,
        "users/1/middle.bin",
        status=FileStatus.READY,
    )
    middle.created_at = datetime(2026, 8, 4, 11, 0)

    newest = _build_resource(
        owner.id,
        "users/1/newest.bin",
        status=FileStatus.READY,
    )
    newest.created_at = datetime(2026, 8, 4, 12, 0)

    pending = _build_resource(
        owner.id,
        "users/1/pending-list.bin",
    )
    pending.created_at = datetime(2026, 8, 4, 13, 0)

    other_users_file = _build_resource(
        other_user.id,
        "users/2/other.bin",
        status=FileStatus.READY,
    )
    other_users_file.created_at = datetime(2026, 8, 4, 14, 0)

    deleted = _build_resource(
        owner.id,
        "users/1/deleted-list.bin",
        status=FileStatus.READY,
        deleted_at=datetime(2026, 8, 4, 15, 0),
    )

    for resource in [
        oldest,
        middle,
        newest,
        pending,
        other_users_file,
        deleted,
    ]:
        repository.create(resource)

    first_page = repository.list_owned(
        owner.id,
        limit=2,
        offset=0,
    )
    second_page = repository.list_owned(
        owner.id,
        limit=2,
        offset=2,
    )

    assert [resource.id for resource in first_page] == [
        newest.id,
        middle.id,
    ]
    assert [resource.id for resource in second_page] == [
        oldest.id,
    ]


def test_update_status_persists_failure_reason(
    session: Session,
) -> None:
    repository = FileRepository(session)
    owner = _create_user(session, "failed-file@example.com")
    resource = repository.create(_build_resource(owner.id, "users/1/failed.bin"))

    repository.update_status(
        resource,
        FileStatus.UPLOAD_FAILED,
        failure_reason="provider_write_failed",
    )
    file_id = resource.id

    session.expire_all()
    persisted = session.get(FileResource, file_id)

    assert persisted is not None
    assert persisted.status == FileStatus.UPLOAD_FAILED.value
    assert persisted.failure_reason == "provider_write_failed"


def test_update_status_persists_deleted_at(
    session: Session,
) -> None:
    repository = FileRepository(session)
    owner = _create_user(session, "deleted-file@example.com")
    resource = repository.create(
        _build_resource(
            owner.id,
            "users/1/deleted-status.bin",
            status=FileStatus.READY,
        )
    )
    deleted_at = datetime(2026, 8, 4, 15, 0)

    repository.update_status(
        resource,
        FileStatus.DELETED,
        deleted_at=deleted_at,
    )
    file_id = resource.id

    session.expire_all()
    persisted = session.get(FileResource, file_id)

    assert persisted is not None
    assert persisted.status == FileStatus.DELETED.value
    assert persisted.deleted_at == deleted_at
