from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.file_resource import FileResource, FileStatus


class FileRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, resource: FileResource) -> FileResource:
        self._session.add(resource)
        self._session.flush()
        self._session.refresh(resource)
        return resource

    def get_owned(
        self,
        file_id: str,
        owner_id: int,
    ) -> FileResource | None:
        statement = select(FileResource).where(
            FileResource.id == file_id,
            FileResource.owner_id == owner_id,
            FileResource.status == FileStatus.READY.value,
            FileResource.deleted_at.is_(None),
        )
        return self._session.scalar(statement)

    def list_owned(
        self,
        owner_id: int,
        *,
        limit: int,
        offset: int,
    ) -> list[FileResource]:
        statement = (
            select(FileResource)
            .where(
                FileResource.owner_id == owner_id,
                FileResource.status == FileStatus.READY.value,
                FileResource.deleted_at.is_(None),
            )
            .order_by(
                FileResource.created_at.desc(),
                FileResource.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return list(self._session.scalars(statement))

    def update_status(
        self,
        resource: FileResource,
        status: FileStatus,
        *,
        failure_reason: str | None = None,
        deleted_at: datetime | None = None,
    ) -> FileResource:
        resource.status = status.value
        resource.failure_reason = failure_reason
        resource.deleted_at = deleted_at

        self._session.flush()
        self._session.refresh(resource)
        return resource
