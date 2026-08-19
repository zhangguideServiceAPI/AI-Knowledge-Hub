from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    # 表级规则中的列名决定约束作用范围；name= 只是在数据库中给规则命名，
    # 便于 Alembic 生成/删除约束，也便于从数据库错误定位规则。
    __table_args__ = (
        # active_version_id 必须属于当前 Document；use_alter=True 用于处理
        # Document 与 Version 互相引用的建表顺序。
        ForeignKeyConstraint(
            ["id", "active_version_id"],
            ["document_versions.document_id", "document_versions.id"],
            name="fk_knowledge_documents_active_version_document_versions",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        # 一个 FileResource 在同一个 KnowledgeBase 中只能登记一次；
        # 同一文件加入不同知识库仍然允许，因为 knowledge_base_id 不同。
        UniqueConstraint(
            "knowledge_base_id",
            "file_id",
            name="uq_knowledge_documents_knowledge_base_file",
        ),
        # 支持按知识库分页列出 Document，并保持稳定的创建顺序。
        Index(
            "ix_knowledge_documents_knowledge_base_created_at",
            "knowledge_base_id",
            "created_at",
        ),
        # 删除 FileResource 前需要快速确认是否仍被 Document 引用。
        Index("ix_knowledge_documents_file_id", "file_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    knowledge_base_id: Mapped[str] = mapped_column(
        ForeignKey(
            "knowledge_bases.id",
            name="fk_knowledge_documents_knowledge_base_id_knowledge_bases",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    file_id: Mapped[str] = mapped_column(
        ForeignKey(
            "files.id",
            name="fk_knowledge_documents_file_id_files",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    active_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
