"""知识修订的业务审批事实；不承载 DocumentVersion 的索引技术状态。"""

from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KnowledgeRevisionStatus(StrEnum):
    """提交后由人工审批维护的业务状态，不与索引状态混用。"""

    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class KnowledgeRevision(Base):
    """一次绑定 DocumentVersion、审批决定和 WorkflowRun 的知识修订。"""

    __tablename__ = "knowledge_revisions"

    __table_args__ = (
        Index(
            "ix_knowledge_revisions_owner_status_expires_at",
            "owner_id",
            "status",
            "expires_at",
        ),
        CheckConstraint(
            "status IN ('submitted', 'approved', 'rejected', 'expired')",
            name="ck_knowledge_revisions_status",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    owner_id: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            name="fk_knowledge_revisions_owner_id_users",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey(
            "knowledge_documents.id",
            name="fk_knowledge_revisions_document_id_knowledge_documents",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    document_version_id: Mapped[str] = mapped_column(
        ForeignKey(
            "document_versions.id",
            name="fk_knowledge_revisions_document_version_id_document_versions",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    workflow_run_id: Mapped[str] = mapped_column(
        ForeignKey(
            "workflow_runs.id",
            name="fk_knowledge_revisions_workflow_run_id_workflow_runs",
            ondelete="RESTRICT",
        ),
        nullable=False,
        unique=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=KnowledgeRevisionStatus.SUBMITTED.value,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    decided_by: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            name="fk_knowledge_revisions_decided_by_users",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
