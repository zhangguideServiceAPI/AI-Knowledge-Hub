"""create knowledge bases table

Revision ID: bf1a4c97e8d3
Revises: 575175576c72
Create Date: 2026-08-17 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "bf1a4c97e8d3"
down_revision: Union[str, None] = "575175576c72"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """向前迁移：创建 KnowledgeBase 表及其所有权、名称和状态约束。"""

    op.create_table(
        "knowledge_bases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "name <> ''",
            name="ck_knowledge_bases_name_non_empty",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name="fk_knowledge_bases_owner_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_knowledge_bases_owner_created_at",
        "knowledge_bases",
        ["owner_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """向后迁移：删除本版本创建的 KnowledgeBase 表。"""

    op.drop_table("knowledge_bases")
