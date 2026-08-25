"""create workflow execution tables

Revision ID: e6f4c13e2a7b
Revises: d4eb9a63f125
Create Date: 2026-08-25 18:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e6f4c13e2a7b"
down_revision: Union[str, None] = "d4eb9a63f125"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """向前迁移：创建 WorkflowRun、StepRun 和 Attempt 的持久化事实表。"""

    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("definition_key", sa.String(length=128), nullable=False),
        sa.Column("definition_version", sa.Integer(), nullable=False),
        sa.Column("run_input", sa.JSON(), nullable=False),
        sa.Column(
            "status", sa.String(length=32), server_default="pending", nullable=False
        ),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "definition_key <> ''",
            name="ck_workflow_runs_definition_key_non_empty",
        ),
        sa.CheckConstraint(
            "definition_version > 0",
            name="ck_workflow_runs_definition_version_positive",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'waiting_approval', 'succeeded', 'failed', 'cancelled')",
            name="ck_workflow_runs_status",
        ),
        sa.CheckConstraint(
            "(status = 'failed' AND failure_code IS NOT NULL) OR "
            "(status <> 'failed' AND failure_code IS NULL)",
            name="ck_workflow_runs_failure_code",
        ),
        sa.CheckConstraint(
            "failure_code IS NULL OR failure_code <> ''",
            name="ck_workflow_runs_failure_code_non_empty",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name="fk_workflow_runs_owner_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_workflow_runs_owner_status_created_at",
        "workflow_runs",
        ["owner_id", "status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_workflow_runs_definition_key_version",
        "workflow_runs",
        ["definition_key", "definition_version"],
        unique=False,
    )

    op.create_table(
        "workflow_step_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workflow_run_id", sa.String(length=36), nullable=False),
        sa.Column("step_id", sa.String(length=128), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column(
            "status", sa.String(length=32), server_default="pending", nullable=False
        ),
        sa.Column("output_payload", sa.JSON(), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "step_id <> ''",
            name="ck_workflow_step_runs_step_id_non_empty",
        ),
        sa.CheckConstraint(
            "step_index >= 0",
            name="ck_workflow_step_runs_step_index_non_negative",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'waiting', 'succeeded', 'failed', 'cancelled')",
            name="ck_workflow_step_runs_status",
        ),
        sa.CheckConstraint(
            "(status = 'failed' AND failure_code IS NOT NULL) OR "
            "(status <> 'failed' AND failure_code IS NULL)",
            name="ck_workflow_step_runs_failure_code",
        ),
        sa.CheckConstraint(
            "failure_code IS NULL OR failure_code <> ''",
            name="ck_workflow_step_runs_failure_code_non_empty",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"],
            ["workflow_runs.id"],
            name="fk_workflow_step_runs_run_id_workflow_runs",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workflow_run_id",
            "step_id",
            name="uq_workflow_step_runs_run_step_id",
        ),
        sa.UniqueConstraint(
            "workflow_run_id",
            "step_index",
            name="uq_workflow_step_runs_run_step_index",
        ),
    )
    op.create_index(
        "ix_workflow_step_runs_run_status_step_index",
        "workflow_step_runs",
        ["workflow_run_id", "status", "step_index"],
        unique=False,
    )

    op.create_table(
        "workflow_attempts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workflow_step_run_id", sa.String(length=36), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column(
            "status", sa.String(length=32), server_default="running", nullable=False
        ),
        sa.Column("output_payload", sa.JSON(), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column(
            "started_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "attempt_number > 0",
            name="ck_workflow_attempts_attempt_number_positive",
        ),
        sa.CheckConstraint(
            "status IN ('running', 'waiting', 'succeeded', 'failed', 'cancelled')",
            name="ck_workflow_attempts_status",
        ),
        sa.CheckConstraint(
            "(status = 'failed' AND failure_code IS NOT NULL) OR "
            "(status <> 'failed' AND failure_code IS NULL)",
            name="ck_workflow_attempts_failure_code",
        ),
        sa.CheckConstraint(
            "failure_code IS NULL OR failure_code <> ''",
            name="ck_workflow_attempts_failure_code_non_empty",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_step_run_id"],
            ["workflow_step_runs.id"],
            name="fk_workflow_attempts_step_run_id_workflow_step_runs",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workflow_step_run_id",
            "attempt_number",
            name="uq_workflow_attempts_step_run_attempt_number",
        ),
    )
    op.create_index(
        "ix_workflow_attempts_step_run_status_attempt_number",
        "workflow_attempts",
        ["workflow_step_run_id", "status", "attempt_number"],
        unique=False,
    )


def downgrade() -> None:
    """向后迁移：按外键依赖反序删除 Attempt、StepRun 与 WorkflowRun 表。"""

    op.drop_table("workflow_attempts")
    op.drop_table("workflow_step_runs")
    op.drop_table("workflow_runs")
