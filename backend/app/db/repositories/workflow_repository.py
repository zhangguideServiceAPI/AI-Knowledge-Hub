"""Workflow 执行状态的数据访问；调用方负责每段短事务的提交。"""

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.workflow import WorkflowAttempt, WorkflowRun, WorkflowStepRun
from app.workflow.state_machine import (
    WorkflowAttemptStatus,
    WorkflowRunStatus,
    WorkflowStepRunStatus,
)


class WorkflowRepository:
    """封装 Run、StepRun 与 Attempt 的查询和条件状态写入。"""

    def __init__(self, session: Session) -> None:
        """保存当前短事务使用的 Session；Repository 不自行 commit。"""

        self._session = session

    def get_run(self, run_id: str) -> WorkflowRun | None:
        """按 ID 读取 WorkflowRun；不存在时返回 None。"""

        return self._session.scalar(select(WorkflowRun).where(WorkflowRun.id == run_id))

    def get_owned_run(self, *, run_id: str, owner_id: int) -> WorkflowRun | None:
        """按 Run 与所有者读取长期事实，避免上层先得到越权的 Workflow 状态。"""

        statement = select(WorkflowRun).where(
            WorkflowRun.id == run_id,
            WorkflowRun.owner_id == owner_id,
        )
        return self._session.scalar(statement)

    def get_failed_step(self, run_id: str) -> WorkflowStepRun | None:
        """读取最早失败 Step，普通 resume 只允许从这个已知失败边界继续。"""

        statement = (
            select(WorkflowStepRun)
            .where(
                WorkflowStepRun.workflow_run_id == run_id,
                WorkflowStepRun.status == WorkflowStepRunStatus.FAILED.value,
            )
            .order_by(WorkflowStepRun.step_index)
        )
        return self._session.scalar(statement)

    def get_step(self, *, run_id: str, step_id: str) -> WorkflowStepRun | None:
        """按稳定 Definition Step ID 读取当前 Run 的单条 Step 事实。"""

        statement = select(WorkflowStepRun).where(
            WorkflowStepRun.workflow_run_id == run_id,
            WorkflowStepRun.step_id == step_id,
        )
        return self._session.scalar(statement)

    def create_run(self, run: WorkflowRun) -> WorkflowRun:
        """加入新的 WorkflowRun 并 flush；调用方决定提交时机。"""

        self._session.add(run)
        self._session.flush()
        self._session.refresh(run)
        return run

    def create_step(self, step: WorkflowStepRun) -> WorkflowStepRun:
        """加入新的 StepRun 并 flush，供同一短事务的状态迁移引用。"""

        self._session.add(step)
        self._session.flush()
        self._session.refresh(step)
        return step

    def approve_waiting_run_and_step(
        self, *, run_id: str, step_id: str, output_payload: dict[str, object]
    ) -> bool:
        """原子完成 waiting 审批 Step，并将 waiting_approval Run 恢复为 running。"""

        step_result = self._session.execute(
            update(WorkflowStepRun)
            .where(
                WorkflowStepRun.id == step_id,
                WorkflowStepRun.workflow_run_id == run_id,
                WorkflowStepRun.status == WorkflowStepRunStatus.WAITING.value,
            )
            .values(
                status=WorkflowStepRunStatus.SUCCEEDED.value,
                output_payload=output_payload,
                failure_code=None,
            )
        )
        run_result = self._session.execute(
            update(WorkflowRun)
            .where(
                WorkflowRun.id == run_id,
                WorkflowRun.status == WorkflowRunStatus.WAITING_APPROVAL.value,
            )
            .values(status=WorkflowRunStatus.RUNNING.value, failure_code=None)
        )
        return step_result.rowcount == 1 and run_result.rowcount == 1

    def cancel_waiting_run_and_step(self, *, run_id: str, step_id: str) -> bool:
        """原子取消等待审批的 Run/Step，供拒绝与惰性过期共同使用。"""

        step_result = self._session.execute(
            update(WorkflowStepRun)
            .where(
                WorkflowStepRun.id == step_id,
                WorkflowStepRun.workflow_run_id == run_id,
                WorkflowStepRun.status == WorkflowStepRunStatus.WAITING.value,
            )
            .values(status=WorkflowStepRunStatus.CANCELLED.value, failure_code=None)
        )
        run_result = self._session.execute(
            update(WorkflowRun)
            .where(
                WorkflowRun.id == run_id,
                WorkflowRun.status == WorkflowRunStatus.WAITING_APPROVAL.value,
            )
            .values(status=WorkflowRunStatus.CANCELLED.value, failure_code=None)
        )
        return step_result.rowcount == 1 and run_result.rowcount == 1

    def get_next_pending_step(self, run_id: str) -> WorkflowStepRun | None:
        """读取当前 Run 中最靠前的 pending Step，供顺序执行器认领。"""

        statement = (
            select(WorkflowStepRun)
            .where(
                WorkflowStepRun.workflow_run_id == run_id,
                WorkflowStepRun.status == WorkflowStepRunStatus.PENDING.value,
            )
            .order_by(WorkflowStepRun.step_index)
        )
        return self._session.scalar(statement)

    def get_latest_succeeded_step_before(
        self, run_id: str, step_index: int
    ) -> WorkflowStepRun | None:
        """读取当前 Step 之前最后一个成功输出，作为受控映射的唯一上游来源。"""

        statement = (
            select(WorkflowStepRun)
            .where(
                WorkflowStepRun.workflow_run_id == run_id,
                WorkflowStepRun.status == WorkflowStepRunStatus.SUCCEEDED.value,
                WorkflowStepRun.step_index < step_index,
            )
            .order_by(WorkflowStepRun.step_index.desc())
        )
        return self._session.scalar(statement)

    def claim_step(self, step_id: str) -> bool:
        """原子认领 pending Step；并发调用中只有一个调用方得到 True。"""

        result = self._session.execute(
            update(WorkflowStepRun)
            .where(
                WorkflowStepRun.id == step_id,
                WorkflowStepRun.status == WorkflowStepRunStatus.PENDING.value,
            )
            .values(status=WorkflowStepRunStatus.RUNNING.value, failure_code=None)
        )
        return result.rowcount == 1

    def get_attempt_count(self, step_id: str) -> int:
        """返回该 Step 已存在的 Attempt 数量；认领成功后可安全据此创建下一次。"""

        count = self._session.scalar(
            select(func.count())
            .select_from(WorkflowAttempt)
            .where(WorkflowAttempt.workflow_step_run_id == step_id)
        )
        return count or 0

    def create_attempt(self, attempt: WorkflowAttempt) -> WorkflowAttempt:
        """将 Attempt 加入当前事务并 flush，保留调用方的提交控制。"""

        self._session.add(attempt)
        self._session.flush()
        self._session.refresh(attempt)
        return attempt

    def complete_attempt_and_step(
        self,
        *,
        attempt_id: str,
        step_id: str,
        output_payload: dict[str, object],
    ) -> bool:
        """把 running Attempt 和 Step 同时推进为 succeeded；任一竞争失败则返回 False。"""

        attempt_result = self._session.execute(
            update(WorkflowAttempt)
            .where(
                WorkflowAttempt.id == attempt_id,
                WorkflowAttempt.status == WorkflowAttemptStatus.RUNNING.value,
            )
            .values(
                status=WorkflowAttemptStatus.SUCCEEDED.value,
                output_payload=output_payload,
                failure_code=None,
                finished_at=func.now(),
            )
        )
        step_result = self._session.execute(
            update(WorkflowStepRun)
            .where(
                WorkflowStepRun.id == step_id,
                WorkflowStepRun.status == WorkflowStepRunStatus.RUNNING.value,
            )
            .values(
                status=WorkflowStepRunStatus.SUCCEEDED.value,
                output_payload=output_payload,
                failure_code=None,
            )
        )
        return attempt_result.rowcount == 1 and step_result.rowcount == 1

    def fail_attempt_step_and_run(
        self,
        *,
        attempt_id: str,
        step_id: str,
        run_id: str,
        failure_code: str,
    ) -> bool:
        """在一个短事务内持久化失败 Attempt、Step 与整体 Run 的稳定错误码。"""

        attempt_result = self._session.execute(
            update(WorkflowAttempt)
            .where(
                WorkflowAttempt.id == attempt_id,
                WorkflowAttempt.status == WorkflowAttemptStatus.RUNNING.value,
            )
            .values(
                status=WorkflowAttemptStatus.FAILED.value,
                failure_code=failure_code,
                finished_at=func.now(),
            )
        )
        step_result = self._session.execute(
            update(WorkflowStepRun)
            .where(
                WorkflowStepRun.id == step_id,
                WorkflowStepRun.status == WorkflowStepRunStatus.RUNNING.value,
            )
            .values(
                status=WorkflowStepRunStatus.FAILED.value, failure_code=failure_code
            )
        )
        run_result = self._session.execute(
            update(WorkflowRun)
            .where(
                WorkflowRun.id == run_id,
                WorkflowRun.status == WorkflowRunStatus.RUNNING.value,
            )
            .values(status=WorkflowRunStatus.FAILED.value, failure_code=failure_code)
        )
        return (
            attempt_result.rowcount == 1
            and step_result.rowcount == 1
            and run_result.rowcount == 1
        )

    def requeue_failed_run_and_step(self, *, run_id: str, step_id: str) -> bool:
        """原子重开可重试失败的 Run/Step；Attempt 历史保留，下一次会创建 A2。"""

        run_result = self._session.execute(
            update(WorkflowRun)
            .where(
                WorkflowRun.id == run_id,
                WorkflowRun.status == WorkflowRunStatus.FAILED.value,
            )
            .values(status=WorkflowRunStatus.RUNNING.value, failure_code=None)
        )
        step_result = self._session.execute(
            update(WorkflowStepRun)
            .where(
                WorkflowStepRun.id == step_id,
                WorkflowStepRun.workflow_run_id == run_id,
                WorkflowStepRun.status == WorkflowStepRunStatus.FAILED.value,
            )
            .values(status=WorkflowStepRunStatus.PENDING.value, failure_code=None)
        )
        return run_result.rowcount == 1 and step_result.rowcount == 1

    def complete_run_if_no_pending_steps(self, run_id: str) -> bool:
        """仅在没有 pending Step 时将 running Run 收口为 succeeded。"""

        pending_step_exists = (
            select(WorkflowStepRun.id)
            .where(
                WorkflowStepRun.workflow_run_id == run_id,
                WorkflowStepRun.status == WorkflowStepRunStatus.PENDING.value,
            )
            .exists()
        )
        result = self._session.execute(
            update(WorkflowRun)
            .where(
                WorkflowRun.id == run_id,
                WorkflowRun.status == WorkflowRunStatus.RUNNING.value,
                ~pending_step_exists,
            )
            .values(status=WorkflowRunStatus.SUCCEEDED.value, failure_code=None)
        )
        return result.rowcount == 1
