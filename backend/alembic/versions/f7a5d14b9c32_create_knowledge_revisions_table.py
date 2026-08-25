"""create knowledge revisions table

Revision ID: f7a5d14b9c32
Revises: e6f4c13e2a7b
Create Date: 2026-08-25 20:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f7a5d14b9c32"
down_revision: Union[str, None] = "e6f4c13e2a7b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建业务审批 Revision 表，独立于 DocumentVersion 的技术索引状态。"""

    op.create_table(
        "knowledge_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("document_version_id", sa.String(length=36), nullable=False),
        sa.Column("workflow_run_id", sa.String(length=36), nullable=False),
        sa.Column(
            "status", sa.String(length=32), server_default="submitted", nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("decided_by", sa.Integer(), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('submitted', 'approved', 'rejected', 'expired')",
            name="ck_knowledge_revisions_status",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name="fk_knowledge_revisions_owner_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["knowledge_documents.id"],
            name="fk_knowledge_revisions_document_id_knowledge_documents",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            name="fk_knowledge_revisions_document_version_id_document_versions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"],
            ["workflow_runs.id"],
            name="fk_knowledge_revisions_workflow_run_id_workflow_runs",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"],
            ["users.id"],
            name="fk_knowledge_revisions_decided_by_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workflow_run_id"),
    )
    op.create_index(
        "ix_knowledge_revisions_owner_status_expires_at",
        "knowledge_revisions",
        ["owner_id", "status", "expires_at"],
        unique=False,
    )


def downgrade() -> None:
    """删除独立审批事实表；降级会丢失 Revision 审计记录。"""

    op.drop_table("knowledge_revisions")
