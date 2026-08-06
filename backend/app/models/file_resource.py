from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FileStatus(StrEnum):
    PENDING_UPLOAD = "pending_upload"
    READY = "ready"
    UPLOAD_FAILED = "upload_failed"
    DELETING = "deleting"
    DELETED = "deleted"
    CLEANUP_REQUIRED = "cleanup_required"


class FileFailureReason(StrEnum):
    PROVIDER_WRITE_FAILED = "provider_write_failed"
    CLEANUP_FAILED = "cleanup_failed"
    METADATA_COMMIT_FAILED = "metadata_commit_failed"
    PROVIDER_DELETE_FAILED = "provider_delete_failed"
    METADATA_DELETE_COMMIT_FAILED = "metadata_delete_commit_failed"
    STORAGE_OBJECT_MISSING = "storage_object_missing"


class FileResource(Base):
    __tablename__ = "files"

    __table_args__ = (
        UniqueConstraint(
            "storage_provider",
            "bucket",
            "object_key",
            name="uq_files_storage_location",
        ),
        Index(
            "ix_files_owner_status_created_at",
            "owner_id",
            "status",
            "created_at",
        ),
        Index("ix_files_sha256", "sha256"),
        CheckConstraint(
            "size_bytes >= 0",
            name="ck_files_size_bytes_non_negative",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    owner_id: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            name="fk_files_owner_id_users",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    storage_provider: Mapped[str] = mapped_column(String(20), nullable=False)
    bucket: Mapped[str] = mapped_column(String(63), nullable=False)
    object_key: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=FileStatus.PENDING_UPLOAD.value,
    )
    failure_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
