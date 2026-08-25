"""Workflow 的恢复用例：权限、重试策略与短事务由 Service 统一编排。"""

from dataclasses import dataclass

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.repositories.workflow_repository import WorkflowRepository
from app.models.workflow import WorkflowRun, WorkflowStepRun
from app.workflow.exceptions import (
    WorkflowRetryExhaustedError,
    WorkflowRunNotFoundError,
    WorkflowRunNotRetryableError,
)
from app.workflow.registry import WorkflowDefinitionRegistry
from app.workflow.state_machine import WorkflowRunStatus

_RETRYABLE_FAILURE_CODES = frozenset({"node_retryable"})


@dataclass(frozen=True)
class WorkflowResumeResult:
    """一次 resume 的结果：是否实际重开，以及当前 Run/Step 的持久化事实。"""

    run: WorkflowRun
    step: WorkflowStepRun | None
    resumed: bool


class WorkflowService:
    """协调 Workflow 恢复，不执行 Node、不开启外部网络调用。"""

    def __init__(
        self, session: Session, definition_registry: WorkflowDefinitionRegistry
    ) -> None:
        """注入请求 Session 与已验证 Definition Registry；Repository 保持只做数据访问。"""

        self._session = session
        self._repository = WorkflowRepository(session)
        self._definition_registry = definition_registry

    def resume_failed_run(self, *, owner_id: int, run_id: str) -> WorkflowResumeResult:
        """只将可重试失败 Run 的最早失败 Step 重排队；成功/进行中 Run 不会重放。"""

        run = self._get_owned_run(owner_id=owner_id, run_id=run_id)
        status = WorkflowRunStatus(run.status)
        if status is WorkflowRunStatus.SUCCEEDED:
            return WorkflowResumeResult(run=run, step=None, resumed=False)
        if status is WorkflowRunStatus.RUNNING:
            return WorkflowResumeResult(run=run, step=None, resumed=False)
        if status is not WorkflowRunStatus.FAILED:
            raise WorkflowRunNotRetryableError("WorkflowRun is not resumable.")
        if run.failure_code not in _RETRYABLE_FAILURE_CODES:
            raise WorkflowRunNotRetryableError("Workflow failure is not retryable.")

        step = self._repository.get_failed_step(run.id)
        if step is None:
            raise WorkflowRunNotRetryableError(
                "WorkflowRun has no failed Step to resume."
            )
        definition = self._definition_registry.get(
            run.definition_key, run.definition_version
        )
        definition_step = definition.step_by_id(step.step_id)
        if self._repository.get_attempt_count(step.id) >= definition_step.max_attempts:
            raise WorkflowRetryExhaustedError("Workflow Step retry limit is exhausted.")

        try:
            resumed = self._repository.requeue_failed_run_and_step(
                run_id=run.id, step_id=step.id
            )
            if resumed:
                self._session.commit()
                return WorkflowResumeResult(run=run, step=step, resumed=True)
            self._session.rollback()
        except SQLAlchemyError:
            self._session.rollback()
            raise

        current = self._get_owned_run(owner_id=owner_id, run_id=run_id)
        if WorkflowRunStatus(current.status) in {
            WorkflowRunStatus.RUNNING,
            WorkflowRunStatus.SUCCEEDED,
        }:
            return WorkflowResumeResult(run=current, step=None, resumed=False)
        raise WorkflowRunNotRetryableError("WorkflowRun changed during resume.")

    def _get_owned_run(self, *, owner_id: int, run_id: str) -> WorkflowRun:
        """读取当前用户的 Run；查不到时不区分不存在与越权。"""

        run = self._repository.get_owned_run(run_id=run_id, owner_id=owner_id)
        if run is None:
            raise WorkflowRunNotFoundError()
        return run
