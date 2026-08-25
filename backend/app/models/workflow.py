"""Workflow 持久化状态的 ORM 模型。

本模块只保存 Workflow 的长期执行事实，不包含 Definition Registry、Node、
Executor 或业务 Service；这些职责分别属于后续 Story。
"""

from datetime import datetime
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
from app.workflow.state_machine import (
    WorkflowAttemptStatus,
    WorkflowRunStatus,
    WorkflowStepRunStatus,
)


class WorkflowRun(Base):
    """一次绑定不可变 Definition 版本的整体 Workflow 执行记录。"""

    __tablename__ = "workflow_runs"

    __table_args__ = (
        # 按所有者查看近期 Run 和终态时使用；不把 Redis 当成执行状态真相。
        Index(
            "ix_workflow_runs_owner_status_created_at",
            "owner_id",
            "status",
            "created_at",
        ),
        # 支持按历史 Definition 版本审计或恢复 Run。
        Index(
            "ix_workflow_runs_definition_key_version",
            "definition_key",
            "definition_version",
        ),
        CheckConstraint(
            "definition_key <> ''",
            name="ck_workflow_runs_definition_key_non_empty",
        ),
        CheckConstraint(
            "definition_version > 0",
            name="ck_workflow_runs_definition_version_positive",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'waiting_approval', 'succeeded', 'failed', 'cancelled')",
            name="ck_workflow_runs_status",
        ),
        # 失败才记录稳定错误码，避免成功或取消的 Run 带着过期失败信息。
        CheckConstraint(
            "(status = 'failed' AND failure_code IS NOT NULL) OR "
            "(status <> 'failed' AND failure_code IS NULL)",
            name="ck_workflow_runs_failure_code",
        ),
        CheckConstraint(
            "failure_code IS NULL OR failure_code <> ''",
            name="ck_workflow_runs_failure_code_non_empty",
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
            name="fk_workflow_runs_owner_id_users",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    # 这两个字段是 Definition 的不可变身份；后续 Service 不允许修改已创建 Run 的绑定。
    definition_key: Mapped[str] = mapped_column(String(128), nullable=False)
    definition_version: Mapped[int] = mapped_column(Integer, nullable=False)
    # JSON 保留经 Schema 校验后的输入快照，不能保存 Secret、Prompt 或 Provider 原始异常。
    run_input: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=WorkflowRunStatus.PENDING.value,
    )
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class WorkflowStepRun(Base):
    """某条 WorkflowRun 中一个固定 Definition Step 的总体执行事实。"""

    __tablename__ = "workflow_step_runs"

    __table_args__ = (
        # step_id 是 Definition 中稳定的语义标识；同一 Run 内不能出现两次。
        UniqueConstraint(
            "workflow_run_id",
            "step_id",
            name="uq_workflow_step_runs_run_step_id",
        ),
        # step_index 保证顺序执行器可以稳定找到下一步，且同一 Run 内顺序唯一。
        UniqueConstraint(
            "workflow_run_id",
            "step_index",
            name="uq_workflow_step_runs_run_step_index",
        ),
        Index(
            "ix_workflow_step_runs_run_status_step_index",
            "workflow_run_id",
            "status",
            "step_index",
        ),
        CheckConstraint(
            "step_id <> ''",
            name="ck_workflow_step_runs_step_id_non_empty",
        ),
        CheckConstraint(
            "step_index >= 0",
            name="ck_workflow_step_runs_step_index_non_negative",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'waiting', 'succeeded', 'failed', 'cancelled')",
            name="ck_workflow_step_runs_status",
        ),
        CheckConstraint(
            "(status = 'failed' AND failure_code IS NOT NULL) OR "
            "(status <> 'failed' AND failure_code IS NULL)",
            name="ck_workflow_step_runs_failure_code",
        ),
        CheckConstraint(
            "failure_code IS NULL OR failure_code <> ''",
            name="ck_workflow_step_runs_failure_code_non_empty",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    workflow_run_id: Mapped[str] = mapped_column(
        ForeignKey(
            "workflow_runs.id",
            name="fk_workflow_step_runs_run_id_workflow_runs",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    step_id: Mapped[str] = mapped_column(String(128), nullable=False)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=WorkflowStepRunStatus.PENDING.value,
    )
    # 只保存安全、有限的节点输出摘要；大结果以后交给 Artifact / File Resource。
    output_payload: Mapped[dict[str, object] | None] = mapped_column(
        JSON, nullable=True
    )
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class WorkflowAttempt(Base):
    """一个 WorkflowStepRun 的第几次真实执行尝试及其最终摘要。"""

    __tablename__ = "workflow_attempts"

    __table_args__ = (
        # A1、A2… 是 Step 内稳定且连续的审计顺序，不是全局重试次数。
        UniqueConstraint(
            "workflow_step_run_id",
            "attempt_number",
            name="uq_workflow_attempts_step_run_attempt_number",
        ),
        Index(
            "ix_workflow_attempts_step_run_status_attempt_number",
            "workflow_step_run_id",
            "status",
            "attempt_number",
        ),
        CheckConstraint(
            "attempt_number > 0",
            name="ck_workflow_attempts_attempt_number_positive",
        ),
        CheckConstraint(
            "status IN ('running', 'waiting', 'succeeded', 'failed', 'cancelled')",
            name="ck_workflow_attempts_status",
        ),
        CheckConstraint(
            "(status = 'failed' AND failure_code IS NOT NULL) OR "
            "(status <> 'failed' AND failure_code IS NULL)",
            name="ck_workflow_attempts_failure_code",
        ),
        CheckConstraint(
            "failure_code IS NULL OR failure_code <> ''",
            name="ck_workflow_attempts_failure_code_non_empty",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    workflow_step_run_id: Mapped[str] = mapped_column(
        ForeignKey(
            "workflow_step_runs.id",
            name="fk_workflow_attempts_step_run_id_workflow_step_runs",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=WorkflowAttemptStatus.RUNNING.value,
    )
    output_payload: Mapped[dict[str, object] | None] = mapped_column(
        JSON, nullable=True
    )
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
