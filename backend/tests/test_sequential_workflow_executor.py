import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.workflow import WorkflowAttempt, WorkflowRun, WorkflowStepRun
from app.workflow.definition import (
    WorkflowDefinition,
    WorkflowInputBinding,
    WorkflowInputSource,
    WorkflowStepDefinition,
)
from app.workflow.executor import SequentialWorkflowExecutor
from app.workflow.node import WorkflowNodeExecutionContext
from app.workflow.registry import WorkflowDefinitionRegistry, WorkflowNodeRegistry
from app.workflow.state_machine import (
    WorkflowAttemptStatus,
    WorkflowRunStatus,
    WorkflowStepRunStatus,
)


class FakeNode:
    """用于验证 Executor 调用边界的同步测试 Node。"""

    node_key = "fake"
    input_type = dict
    output_type = dict

    def __init__(self, error: Exception | None = None) -> None:
        """选择本次调用是返回固定输出还是抛出预期异常。"""

        self.error = error
        self.calls = 0
        self.last_input: dict[str, object] | None = None

    def execute(
        self,
        node_input: dict[str, object],
        context: WorkflowNodeExecutionContext,
    ) -> dict[str, object]:
        """记录调用并返回安全 JSON 摘要，模拟真实 Node 的业务结果。"""

        del context
        self.calls += 1
        self.last_input = node_input
        if self.error is not None:
            raise self.error
        return {"echo": node_input["value"]}


def _executor(session: Session, node: FakeNode) -> SequentialWorkflowExecutor:
    """组装一个只有单 Step 的已验证 Definition 与顺序执行器。"""

    definition = WorkflowDefinition(
        key="test",
        version=1,
        input_type=dict,
        start_step_id="step",
        steps=(WorkflowStepDefinition("step", "fake", dict),),
    )
    node_registry = WorkflowNodeRegistry((node,))
    definition_registry = WorkflowDefinitionRegistry(node_registry, (definition,))
    return SequentialWorkflowExecutor(session, definition_registry, node_registry)


def _running_run(
    session: Session, *, run_input: dict[str, object] | None = None
) -> WorkflowRun:
    """创建一个已进入 running 的 Run 与其唯一 pending Step。"""

    owner = User(email="executor@example.com", password_hash="hash")
    session.add(owner)
    session.flush()
    run = WorkflowRun(
        owner_id=owner.id,
        definition_key="test",
        definition_version=1,
        run_input=run_input or {},
        status=WorkflowRunStatus.RUNNING.value,
    )
    session.add(run)
    session.flush()
    session.add(WorkflowStepRun(workflow_run_id=run.id, step_id="step", step_index=0))
    session.commit()
    return run


def test_executor_claims_executes_and_completes_last_step(session: Session) -> None:
    node = FakeNode()
    run = _running_run(session)

    result = _executor(session, node).execute_next(run.id, {"value": "ok"})

    assert result is not None
    assert result.run_status is WorkflowRunStatus.SUCCEEDED
    assert result.output_payload == {"echo": "ok"}
    assert result.next_step_id is None
    assert node.calls == 1


def test_executor_persists_failure_after_node_error(session: Session) -> None:
    run = _running_run(session)

    with pytest.raises(RuntimeError):
        _executor(session, FakeNode(RuntimeError("downstream failed"))).execute_next(
            run.id, {"value": "ok"}
        )

    session.expire_all()
    assert session.get(WorkflowRun, run.id).status == WorkflowRunStatus.FAILED.value
    step = session.scalar(
        select(WorkflowStepRun).where(WorkflowStepRun.workflow_run_id == run.id)
    )
    assert step is not None
    attempt = session.scalar(
        select(WorkflowAttempt).where(WorkflowAttempt.workflow_step_run_id == step.id)
    )
    assert attempt is not None
    assert step.status == WorkflowStepRunStatus.FAILED.value
    assert attempt.status == WorkflowAttemptStatus.FAILED.value
    assert attempt.failure_code == "node_execution_failed"


def test_executor_builds_declared_input_from_durable_run_snapshot(
    session: Session,
) -> None:
    node = FakeNode()
    definition = WorkflowDefinition(
        key="test",
        version=1,
        input_type=dict,
        start_step_id="step",
        steps=(
            WorkflowStepDefinition(
                "step",
                "fake",
                dict,
                input_bindings=(
                    WorkflowInputBinding(
                        "value", WorkflowInputSource.RUN_INPUT, "revision_id"
                    ),
                ),
            ),
        ),
    )
    node_registry = WorkflowNodeRegistry((node,))
    executor = SequentialWorkflowExecutor(
        session,
        WorkflowDefinitionRegistry(node_registry, (definition,)),
        node_registry,
    )
    run = _running_run(session, run_input={"revision_id": "r1"})

    result = executor.execute_next(run.id)

    assert result is not None
    assert node.last_input == {"value": "r1"}
