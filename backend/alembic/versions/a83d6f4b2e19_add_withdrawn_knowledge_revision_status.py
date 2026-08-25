"""add withdrawn knowledge revision status

Revision ID: a83d6f4b2e19
Revises: f7a5d14b9c32
Create Date: 2026-08-25 22:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


revision: str = "a83d6f4b2e19"
down_revision: Union[str, None] = "f7a5d14b9c32"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """把作者撤回加入 Revision 业务状态，不改变 DocumentVersion 技术状态。"""

    op.drop_constraint(
        "ck_knowledge_revisions_status", "knowledge_revisions", type_="check"
    )
    op.create_check_constraint(
        "ck_knowledge_revisions_status",
        "knowledge_revisions",
        "status IN ('submitted', 'approved', 'rejected', 'expired', 'withdrawn')",
    )


def downgrade() -> None:
    """移除作者撤回状态；降级前不得存在 withdrawn Revision。"""

    op.drop_constraint(
        "ck_knowledge_revisions_status", "knowledge_revisions", type_="check"
    )
    op.create_check_constraint(
        "ck_knowledge_revisions_status",
        "knowledge_revisions",
        "status IN ('submitted', 'approved', 'rejected', 'expired')",
    )
