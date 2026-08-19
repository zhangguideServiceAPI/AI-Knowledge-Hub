from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    # 表级规则中列名决定约束范围；name= 是数据库对象名，供 Alembic、
    # 数据库错误和运维工具引用，不会写入 Chunk 内容。
    __table_args__ = (
        # 一个 Version 内的 chunk_index 表示稳定顺序，不能出现重复位置。
        UniqueConstraint(
            "document_version_id",
            "chunk_index",
            name="uq_document_chunks_version_chunk_index",
        ),
        # 索引从 0 开始，便于按原文顺序重建 Context。
        CheckConstraint(
            "chunk_index >= 0",
            name="ck_document_chunks_chunk_index_non_negative",
        ),
        # Token 数不能为负，ContextBuilder 后续会用它计算上下文预算。
        CheckConstraint(
            "token_count >= 0",
            name="ck_document_chunks_token_count_non_negative",
        ),
        # 空文本没有检索价值，也不应产生向量点。
        CheckConstraint(
            "content <> ''",
            name="ck_document_chunks_content_non_empty",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    document_version_id: Mapped[str] = mapped_column(
        ForeignKey(
            "document_versions.id",
            name="fk_document_chunks_document_version_id_document_versions",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source_locator: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
