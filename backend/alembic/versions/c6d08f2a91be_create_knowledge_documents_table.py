"""create knowledge documents table

Revision ID: c6d08f2a91be
Revises: bf1a4c97e8d3
Create Date: 2026-08-17 12:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c6d08f2a91be"
down_revision: Union[str, None] = "bf1a4c97e8d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """向前迁移：创建连接 KnowledgeBase 与 FileResource 的 Document 表。"""

    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("knowledge_base_id", sa.String(length=36), nullable=False),
        sa.Column("file_id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["files.id"],
            name="fk_knowledge_documents_file_id_files",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"],
            ["knowledge_bases.id"],
            name="fk_knowledge_documents_knowledge_base_id_knowledge_bases",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "knowledge_base_id",
            "file_id",
            name="uq_knowledge_documents_knowledge_base_file",
        ),
    )
    op.create_index(
        "ix_knowledge_documents_file_id",
        "knowledge_documents",
        ["file_id"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_documents_knowledge_base_created_at",
        "knowledge_documents",
        ["knowledge_base_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """向后迁移：删除本版本创建的 KnowledgeDocument 表。"""

    op.drop_table("knowledge_documents")
