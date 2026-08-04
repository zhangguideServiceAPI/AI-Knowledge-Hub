from typing import BinaryIO
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.logging import logger
from app.db.repositories.file_repository import FileRepository
from app.models.file_resource import FileResource, FileStatus
from app.schemas.file import FileResourceResponse
from app.storage.provider import StorageProvider
from app.storage.upload_validation import inspect_upload
from app.storage.exceptions import (
    EmptyFileError,
    FileUploadFailedError,
    FileTooLargeError,
    InvalidFileNameError,
    StorageOperationError,
    StorageUnavailableError,
    UnsupportedFileTypeError,
)


class FileService:
    def __init__(
        self,
        session: Session,
        storage_provider: StorageProvider,
        *,
        bucket: str,
        max_upload_size: int,
        chunk_size: int,
    ) -> None:
        self._session = session
        self._repository = FileRepository(session)
        self._storage_provider = storage_provider
        self._bucket = bucket
        self._max_upload_size = max_upload_size
        self._chunk_size = chunk_size

    def upload(
        self,
        *,
        owner_id: int,
        original_filename: str | None,
        content_type: str | None,
        source: BinaryIO,
    ) -> FileResourceResponse:

        try:
            inspected = inspect_upload(
                source=source,
                original_filename=original_filename,
                content_type=content_type,
                max_upload_size=self._max_upload_size,
                chunk_size=self._chunk_size,
            )
        except (
            EmptyFileError,
            FileTooLargeError,
            InvalidFileNameError,
            UnsupportedFileTypeError,
        ) as error:
            logger.warning(
                "storage.upload.rejected user_id=%s reason=%s",
                owner_id,
                type(error).__name__,
            )
            raise

        file_id = str(uuid4())
        object_key = f"users/{owner_id}/{file_id}"

        resource = FileResource(
            id=file_id,
            owner_id=owner_id,
            storage_provider="local",
            bucket=self._bucket,
            object_key=object_key,
            original_filename=inspected.original_filename,
            content_type=inspected.content_type,
            size_bytes=inspected.size_bytes,
            sha256=inspected.sha256,
            status=FileStatus.PENDING_UPLOAD.value,
        )

        self._repository.create(resource)
        self._session.commit()

        try:
            self._storage_provider.put(
                object_key,
                source,
            )
        except StorageOperationError as error:
            logger.error(
                "storage.upload.failed user_id=%s file_id=%s reason=provider_write_failed",
                owner_id,
                file_id,
            )
            self._repository.update_status(
                resource,
                FileStatus.UPLOAD_FAILED,
                failure_reason="provider_write_failed",
            )
            self._session.commit()

            raise StorageUnavailableError() from error

        self._repository.update_status(
            resource,
            FileStatus.READY,
        )
        try:
            self._session.commit()
        except SQLAlchemyError as error:
            self._session.rollback()

            try:
                self._storage_provider.delete(object_key)
            except StorageOperationError as cleanup_error:
                # 对象是否仍存在已经不确定，保留状态供后续清理任务处理。
                logger.error(
                    "storage.upload.failed user_id=%s file_id=%s reason=cleanup_failed",
                    owner_id,
                    file_id,
                )
                self._repository.update_status(
                    resource,
                    FileStatus.CLEANUP_REQUIRED,
                    failure_reason="cleanup_failed",
                )
                self._session.commit()
                raise FileUploadFailedError() from cleanup_error

            self._repository.update_status(
                resource,
                FileStatus.UPLOAD_FAILED,
                failure_reason="metadata_commit_failed",
            )
            self._session.commit()
            logger.error(
                "storage.upload.failed user_id=%s file_id=%s reason=metadata_commit_failed",
                owner_id,
                file_id,
            )

            raise FileUploadFailedError() from error

        logger.info(
            "storage.upload.success user_id=%s file_id=%s size_bytes=%s",
            owner_id,
            file_id,
            inspected.size_bytes,
        )
        return FileResourceResponse.model_validate(resource)
