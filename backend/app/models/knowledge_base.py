from datetime import datetime
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    # __table_args__ 放表级规则；列名参数指向数据列，name= 是数据库对象名，
    # 供迁移、报错和后续删除约束时稳定引用，不是业务字段的值。
    __table_args__ = (
        # 按 owner 查询并按创建时间排序，避免每次列出知识库都全表扫描。
        Index(
            "ix_knowledge_bases_owner_created_at",
            "owner_id",
            "created_at",
        ),
        # 数据库拒绝空字符串；只包含空格的名称由 API Schema 层 strip 后校验。
        CheckConstraint(
            "name <> ''",
            name="ck_knowledge_bases_name_non_empty",
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
            name="fk_knowledge_bases_owner_id_users",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
