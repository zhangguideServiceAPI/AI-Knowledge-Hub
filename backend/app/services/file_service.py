from dataclasses import dataclass
from datetime import datetime
from typing import BinaryIO
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.logging import logger
from app.db.repositories.file_repository import FileRepository
from app.models.file_resource import (
    FileFailureReason,
    FileResource,
    FileStatus,
)
from app.schemas.file import (
    FileResourceListResponse,
    FileResourceResponse,
)
from app.storage.exceptions import (
    EmptyFileError,
    FileCleanupFailedError,
    FileContentUnavailableError,
    FileDeleteFailedError,
    FileResourceNotFoundError,
    FileTooLargeError,
    FileUploadFailedError,
    InvalidFileNameError,
    StorageObjectNotFoundError,
    StorageOperationError,
    StorageUnavailableError,
    UnsupportedFileTypeError,
)
from app.storage.provider import StorageProvider
from app.storage.upload_validation import inspect_upload


@dataclass(frozen=True)
class FileDownload:
    stream: BinaryIO
    original_filename: str
    content_type: str
    size_bytes: int
    chunk_size: int


class FileService:
    def __init__(
        self,
        session: Session,
        storage_provider: StorageProvider,
        *,
        storage_provider_name: str,
        bucket: str,
        max_upload_size: int,
        chunk_size: int,
    ) -> None:
        self._session = session
        self._repository = FileRepository(session)
        self._storage_provider = storage_provider
        self._storage_provider_name = storage_provider_name
        self._bucket = bucket
        self._max_upload_size = max_upload_size
        self._chunk_size = chunk_size

    def _ensure_storage_matches(
        self,
        resource: FileResource,
    ) -> None:
        # Metadata 可能属于其他 Provider，禁止用当前 Provider 误操作对象。
        if (
            resource.storage_provider != self._storage_provider_name
            or resource.bucket != self._bucket
        ):
            logger.error(
                "storage.provider.mismatch file_id=%s",
                resource.id,
            )
            raise StorageUnavailableError()

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
            storage_provider=self._storage_provider_name,
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
            # 写入报错不代表对象一定不存在，因此先执行幂等删除。
            try:
                self._storage_provider.delete(object_key)
            except StorageOperationError as cleanup_error:
                logger.error(
                    "storage.upload.failed user_id=%s file_id=%s reason=cleanup_failed",
                    owner_id,
                    file_id,
                )
                self._repository.update_status(
                    resource,
                    FileStatus.CLEANUP_REQUIRED,
                    failure_reason=FileFailureReason.CLEANUP_FAILED.value,
                )
                self._session.commit()

                raise StorageUnavailableError() from cleanup_error

            logger.error(
                "storage.upload.failed user_id=%s file_id=%s reason=provider_write_failed",
                owner_id,
                file_id,
            )
            self._repository.update_status(
                resource,
                FileStatus.UPLOAD_FAILED,
                failure_reason=FileFailureReason.PROVIDER_WRITE_FAILED.value,
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
                    failure_reason=FileFailureReason.CLEANUP_FAILED.value,
                )
                self._session.commit()
                raise FileUploadFailedError() from cleanup_error

            self._repository.update_status(
                resource,
                FileStatus.UPLOAD_FAILED,
                failure_reason=FileFailureReason.METADATA_COMMIT_FAILED.value,
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

    def get_file(
        self,
        *,
        owner_id: int,
        file_id: str,
    ) -> FileResourceResponse:
        resource = self._repository.get_owned(
            file_id=file_id,
            owner_id=owner_id,
        )

        if resource is None:
            raise FileResourceNotFoundError()

        return FileResourceResponse.model_validate(resource)

    def list_files(
        self,
        *,
        owner_id: int,
        limit: int,
        offset: int,
    ) -> FileResourceListResponse:
        resources = self._repository.list_owned(
            owner_id=owner_id,
            limit=limit,
            offset=offset,
        )

        return FileResourceListResponse(
            items=[
                FileResourceResponse.model_validate(resource) for resource in resources
            ],
            limit=limit,
            offset=offset,
        )

    def delete_file(
        self,
        *,
        owner_id: int,
        file_id: str,
    ) -> None:
        resource = self._repository.get_owned(
            file_id=file_id,
            owner_id=owner_id,
        )

        if resource is None:
            raise FileResourceNotFoundError()

        self._ensure_storage_matches(resource)

        object_key = resource.object_key

        try:
            self._repository.update_status(
                resource,
                FileStatus.DELETING,
            )
            self._session.commit()
        except SQLAlchemyError as error:
            self._session.rollback()
            logger.error(
                "storage.delete.failed user_id=%s file_id=%s "
                "reason=metadata_deleting_commit_failed",
                owner_id,
                file_id,
            )
            raise FileDeleteFailedError() from error

        try:
            self._storage_provider.delete(object_key)
        except StorageOperationError as error:
            logger.error(
                "storage.delete.failed user_id=%s file_id=%s reason=provider_delete_failed",
                owner_id,
                file_id,
            )

            try:
                self._repository.update_status(
                    resource,
                    FileStatus.CLEANUP_REQUIRED,
                    failure_reason=FileFailureReason.PROVIDER_DELETE_FAILED.value,
                )
                self._session.commit()
            except SQLAlchemyError as state_error:
                self._session.rollback()
                logger.error(
                    "storage.compensation.failed operation=delete file_id=%s "
                    "reason=cleanup_state_commit_failed",
                    file_id,
                )
                raise FileDeleteFailedError() from state_error

            raise StorageUnavailableError() from error

        try:
            self._repository.update_status(
                resource,
                FileStatus.DELETED,
                deleted_at=datetime.now(),
            )
            self._session.commit()
        except SQLAlchemyError as error:
            self._session.rollback()

            try:
                self._repository.update_status(
                    resource,
                    FileStatus.CLEANUP_REQUIRED,
                    failure_reason=(
                        FileFailureReason.METADATA_DELETE_COMMIT_FAILED.value
                    ),
                )
                self._session.commit()
            except SQLAlchemyError as state_error:
                self._session.rollback()
                logger.error(
                    "storage.compensation.failed operation=delete file_id=%s "
                    "reason=cleanup_state_commit_failed",
                    file_id,
                )
                raise FileDeleteFailedError() from state_error

            logger.error(
                "storage.delete.failed user_id=%s file_id=%s "
                "reason=metadata_delete_commit_failed",
                owner_id,
                file_id,
            )
            raise FileDeleteFailedError() from error

        logger.info(
            "storage.delete.success user_id=%s file_id=%s",
            owner_id,
            file_id,
        )

    def download_file(
        self,
        *,
        owner_id: int,
        file_id: str,
    ) -> FileDownload:
        resource = self._repository.get_owned(
            file_id=file_id,
            owner_id=owner_id,
        )

        if resource is None:
            raise FileResourceNotFoundError()

        self._ensure_storage_matches(resource)

        try:
            stream = self._storage_provider.open(resource.object_key)
        except StorageObjectNotFoundError as error:
            logger.error(
                "storage.download.failed user_id=%s file_id=%s reason=storage_object_missing",
                owner_id,
                file_id,
            )

            try:
                self._repository.update_status(
                    resource,
                    FileStatus.CLEANUP_REQUIRED,
                    failure_reason=FileFailureReason.STORAGE_OBJECT_MISSING.value,
                )
                self._session.commit()
            except SQLAlchemyError as state_error:
                self._session.rollback()
                logger.error(
                    "storage.compensation.failed operation=download file_id=%s "
                    "reason=cleanup_state_commit_failed",
                    file_id,
                )
                raise FileContentUnavailableError() from state_error

            raise FileContentUnavailableError() from error
        except StorageOperationError as error:
            logger.error(
                "storage.download.failed user_id=%s file_id=%s reason=provider_read_failed",
                owner_id,
                file_id,
            )
            raise StorageUnavailableError() from error

        return FileDownload(
            stream=stream,
            original_filename=resource.original_filename,
            content_type=resource.content_type,
            size_bytes=resource.size_bytes,
            chunk_size=self._chunk_size,
        )

    def cleanup_file(
        self,
        *,
        file_id: str,
    ) -> bool:
        resource = self._repository.get_cleanup_required(file_id)

        if resource is None:
            return False

        self._ensure_storage_matches(resource)

        upload_cleanup_reasons = {
            FileFailureReason.CLEANUP_FAILED.value,
        }
        delete_cleanup_reasons = {
            FileFailureReason.PROVIDER_DELETE_FAILED.value,
            FileFailureReason.METADATA_DELETE_COMMIT_FAILED.value,
            FileFailureReason.STORAGE_OBJECT_MISSING.value,
        }

        # 必须先判断目标状态，再删除对象。
        if resource.failure_reason in upload_cleanup_reasons:
            target_status = FileStatus.UPLOAD_FAILED
            deleted_at = None
        elif resource.failure_reason in delete_cleanup_reasons:
            target_status = FileStatus.DELETED
            deleted_at = datetime.now()
        else:
            logger.error(
                "storage.cleanup.failed file_id=%s reason=unsupported_failure_reason",
                file_id,
            )
            raise FileCleanupFailedError()

        try:
            self._storage_provider.delete(resource.object_key)
        except StorageOperationError as error:
            logger.error(
                "storage.cleanup.failed file_id=%s reason=provider_delete_failed",
                file_id,
            )
            raise StorageUnavailableError() from error

        try:
            self._repository.update_status(
                resource,
                target_status,
                failure_reason=resource.failure_reason,
                deleted_at=deleted_at,
            )
            self._session.commit()
        except SQLAlchemyError as error:
            self._session.rollback()
            logger.error(
                "storage.cleanup.failed file_id=%s reason=metadata_commit_failed",
                file_id,
            )
            raise FileCleanupFailedError() from error

        logger.info(
            "storage.cleanup.success file_id=%s target_status=%s",
            file_id,
            target_status.value,
        )
        return True
