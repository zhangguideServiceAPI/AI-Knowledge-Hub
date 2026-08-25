"""Story 6.5 对失败 Workflow 的受控恢复与 Attempt 审计测试。"""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.workflow import WorkflowAttempt, WorkflowRun, WorkflowStepRun
from app.services.workflow_service import WorkflowService
from app.workflow.definition import WorkflowDefinition, WorkflowStepDefinition
from app.workflow.exceptions import (
    WorkflowRetryExhaustedError,
    WorkflowRetryableNodeError,
    WorkflowRunNotRetryableError,
)
from app.workflow.executor import SequentialWorkflowExecutor
from app.workflow.node import WorkflowNodeExecutionContext
from app.workflow.registry import WorkflowDefinitionRegistry, WorkflowNodeRegistry
from app.workflow.state_machine import (
    WorkflowAttemptStatus,
    WorkflowRunStatus,
    WorkflowStepRunStatus,
)


class RetryNode:
    """可在第一调用暂时失败、第二调用成功的测试 Node。"""

    node_key = "retry"
    input_type = dict
    output_type = dict

    def __init__(self, failures_remaining: int = 0) -> None:
        """保存还需模拟的可重试失败次数与收到的稳定幂等键。"""

        self.failures_remaining = failures_remaining
        self.idempotency_keys: list[str] = []

    def execute(
        self,
        node_input: dict[str, object],
        context: WorkflowNodeExecutionContext,
    ) -> dict[str, object]:
        """先按配置抛暂时错误，成功时返回有限 JSON 输出。"""

        self.idempotency_keys.append(context.idempotency_key)
        if self.failures_remaining:
            self.failures_remaining -= 1
            raise WorkflowRetryableNodeError("temporary dependency failure")
        return {"value": node_input["value"]}


def _definition_registry(
    node: RetryNode, *, max_attempts: int = 2
) -> WorkflowDefinitionRegistry:
    """组装带明确最大次数的单 Step Definition Registry。"""

    definition = WorkflowDefinition(
        key="retry_test",
        version=1,
        input_type=dict,
        start_step_id="retry_step",
        steps=(
            WorkflowStepDefinition(
                "retry_step", "retry", dict, max_attempts=max_attempts
            ),
        ),
    )
    return WorkflowDefinitionRegistry(WorkflowNodeRegistry((node,)), (definition,))


def _failed_run(session: Session) -> tuple[User, WorkflowRun, WorkflowStepRun]:
    """创建已记录 node_retryable 失败的 Run、Step 与 Attempt A1。"""

    owner = User(email="workflow-retry@example.com", password_hash="hash")
    session.add(owner)
    session.flush()
    run = WorkflowRun(
        owner_id=owner.id,
        definition_key="retry_test",
        definition_version=1,
        run_input={},
        status=WorkflowRunStatus.FAILED.value,
        failure_code="node_retryable",
    )
    session.add(run)
    session.flush()
    step = WorkflowStepRun(
        workflow_run_id=run.id,
        step_id="retry_step",
        step_index=0,
        status=WorkflowStepRunStatus.FAILED.value,
        failure_code="node_retryable",
    )
    session.add(step)
    session.flush()
    session.add(
        WorkflowAttempt(
            workflow_step_run_id=step.id,
            attempt_number=1,
            status=WorkflowAttemptStatus.FAILED.value,
            failure_code="node_retryable",
        )
    )
    session.commit()
    return owner, run, step


def test_resume_requeues_retryable_failure_and_preserves_attempt_history(
    session: Session,
) -> None:
    node = RetryNode()
    registry = _definition_registry(node)
    owner, run, step = _failed_run(session)

    result = WorkflowService(session, registry).resume_failed_run(
        owner_id=owner.id, run_id=run.id
    )

    assert result.resumed is True
    session.expire_all()
    assert session.get(WorkflowRun, run.id).status == WorkflowRunStatus.RUNNING.value
    assert (
        session.get(WorkflowStepRun, step.id).status
        == WorkflowStepRunStatus.PENDING.value
    )
    attempts = session.scalars(
        select(WorkflowAttempt)
        .where(WorkflowAttempt.workflow_step_run_id == step.id)
        .order_by(WorkflowAttempt.attempt_number)
    ).all()
    assert [attempt.attempt_number for attempt in attempts] == [1]


def test_retry_attempt_reuses_step_idempotency_key_and_creates_a2(
    session: Session,
) -> None:
    node = RetryNode(failures_remaining=1)
    node_registry = WorkflowNodeRegistry((node,))
    registry = _definition_registry(node)
    owner = User(email="workflow-a2@example.com", password_hash="hash")
    session.add(owner)
    session.flush()
    run = WorkflowRun(
        owner_id=owner.id,
        definition_key="retry_test",
        definition_version=1,
        run_input={},
        status=WorkflowRunStatus.RUNNING.value,
    )
    session.add(run)
    session.flush()
    session.add(
        WorkflowStepRun(workflow_run_id=run.id, step_id="retry_step", step_index=0)
    )
    session.commit()
    executor = SequentialWorkflowExecutor(session, registry, node_registry)

    with pytest.raises(WorkflowRetryableNodeError):
        executor.execute_next(run.id, {"value": "ok"})
    WorkflowService(session, registry).resume_failed_run(
        owner_id=owner.id, run_id=run.id
    )
    result = executor.execute_next(run.id, {"value": "ok"})

    assert result is not None
    assert node.idempotency_keys[0] == node.idempotency_keys[1]
    step = session.scalar(
        select(WorkflowStepRun).where(WorkflowStepRun.workflow_run_id == run.id)
    )
    assert step is not None
    attempts = session.scalars(
        select(WorkflowAttempt)
        .where(WorkflowAttempt.workflow_step_run_id == step.id)
        .order_by(WorkflowAttempt.attempt_number)
    ).all()
    assert [attempt.attempt_number for attempt in attempts] == [1, 2]


def test_resume_rejects_non_retryable_or_exhausted_run(session: Session) -> None:
    node = RetryNode()
    owner, run, step = _failed_run(session)
    run.failure_code = "node_execution_failed"
    session.commit()

    with pytest.raises(WorkflowRunNotRetryableError):
        WorkflowService(session, _definition_registry(node)).resume_failed_run(
            owner_id=owner.id, run_id=run.id
        )

    run.failure_code = "node_retryable"
    session.add(
        WorkflowAttempt(
            workflow_step_run_id=step.id,
            attempt_number=2,
            status=WorkflowAttemptStatus.FAILED.value,
            failure_code="node_retryable",
        )
    )
    session.commit()
    with pytest.raises(WorkflowRetryExhaustedError):
        WorkflowService(session, _definition_registry(node)).resume_failed_run(
            owner_id=owner.id, run_id=run.id
        )
