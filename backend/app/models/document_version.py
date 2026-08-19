from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DocumentVersionStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    INDEXED = "indexed"
    FAILED = "failed"
    CLEANUP_REQUIRED = "cleanup_required"


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    # 这里的字符串参数是参与约束的列；name= 是数据库约束/索引的稳定标识，
    # 不是 Version 记录中的业务名称。
    __table_args__ = (
        # 复合外键会引用 (document_id, id)，所以保留这个可被引用的列组合。
        UniqueConstraint(
            "document_id",
            "id",
            name="uq_document_versions_id_document",
        ),
        # 同一个 Document 的版本号必须递增且唯一，例如 v1、v2、v3。
        UniqueConstraint(
            "document_id",
            "version_number",
            name="uq_document_versions_document_version_number",
        ),
        # 相同处理配置只创建一个 Version，失败时复用它重试，避免重复索引。
        UniqueConstraint(
            "document_id",
            "processing_fingerprint",
            name="uq_document_versions_document_processing_fingerprint",
        ),
        # 支持查询某个 Document 的处理状态和最近版本。
        Index(
            "ix_document_versions_document_status_created_at",
            "document_id",
            "status",
            "created_at",
        ),
        # 以下 CheckConstraint 把不可为负或不可为空的处理契约下沉到数据库。
        CheckConstraint(
            "version_number > 0",
            name="ck_document_versions_version_number_positive",
        ),
        # fingerprint 用于幂等判断，空值没有去重意义。
        CheckConstraint(
            "processing_fingerprint <> ''",
            name="ck_document_versions_processing_fingerprint_non_empty",
        ),
        # Parser/Chunker/Embedding Profile 是处理配置的快照，不能是空标识。
        CheckConstraint(
            "parser_name <> ''",
            name="ck_document_versions_parser_name_non_empty",
        ),
        CheckConstraint(
            "parser_version <> ''",
            name="ck_document_versions_parser_version_non_empty",
        ),
        CheckConstraint(
            "chunker_name <> ''",
            name="ck_document_versions_chunker_name_non_empty",
        ),
        # Embedding Profile 变化必须形成新的 Version，维度也必须有效。
        CheckConstraint(
            "embedding_profile <> ''",
            name="ck_document_versions_embedding_profile_non_empty",
        ),
        CheckConstraint(
            "embedding_dimension > 0",
            name="ck_document_versions_embedding_dimension_positive",
        ),
        # 只允许定义过的生命周期状态，避免拼写错误产生不可识别状态。
        CheckConstraint(
            "status IN ('pending', 'processing', 'indexed', 'failed', 'cleanup_required')",
            name="ck_document_versions_status",
        ),
        # 失败或需要清理时必须留下错误码；正常状态不应携带失败原因。
        CheckConstraint(
            "(status IN ('failed', 'cleanup_required') AND failure_reason IS NOT NULL) OR (status NOT IN ('failed', 'cleanup_required') AND failure_reason IS NULL)",
            name="ck_document_versions_failure_reason",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey(
            "knowledge_documents.id",
            name="fk_document_versions_document_id_knowledge_documents",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    processing_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    parser_name: Mapped[str] = mapped_column(String(64), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(64), nullable=False)
    chunker_name: Mapped[str] = mapped_column(String(64), nullable=False)
    chunker_config: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    embedding_profile: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=DocumentVersionStatus.PENDING.value,
    )
    failure_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
