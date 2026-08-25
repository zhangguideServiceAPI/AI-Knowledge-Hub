"""顺序执行已验证 Definition 中一个 ready Step 的最小执行器。"""

import logging

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.repositories.workflow_repository import WorkflowRepository
from app.models.workflow import WorkflowAttempt, WorkflowRun, WorkflowStepRun
from app.workflow.definition import WorkflowStepDefinition
from app.workflow.exceptions import (
    WorkflowDefinitionError,
    WorkflowDefinitionTopologyError,
    WorkflowRetryableNodeError,
)
from app.workflow.node import WorkflowNodeExecutionContext
from app.workflow.registry import WorkflowDefinitionRegistry, WorkflowNodeRegistry
from app.workflow.routing import WorkflowRouteResolver
from app.workflow.state_machine import WorkflowRunStatus

logger = logging.getLogger(__name__)

_NODE_EXECUTION_FAILURE = "node_execution_failed"
_NODE_RETRYABLE_FAILURE = "node_retryable"


@dataclass(frozen=True)
class StepExecutionResult:
    """一次顺序 Step 执行后的持久化结果摘要。"""

    run_id: str
    step_id: str
    attempt_number: int
    run_status: WorkflowRunStatus
    output_payload: dict[str, object]
    next_step_id: str | None


class SequentialWorkflowExecutor:
    """用两段短事务认领/收口一个 Step，且绝不在事务中调用 Node。"""

    def __init__(
        self,
        session: Session,
        definition_registry: WorkflowDefinitionRegistry,
        node_registry: WorkflowNodeRegistry,
    ) -> None:
        """注入数据库 Session 与已验证 Registry；不在构造时访问数据库或执行 Node。"""

        self._session = session
        self._repository = WorkflowRepository(session)
        self._definition_registry = definition_registry
        self._node_registry = node_registry
        self._route_resolver = WorkflowRouteResolver()

    def execute_next(
        self, run_id: str, node_input: object | None = None
    ) -> StepExecutionResult | None:
        """认领并执行最早 pending Step；无可执行 Step 时返回 None。"""

        run, step, attempt = self._claim_next_step(run_id)
        if run is None or step is None or attempt is None:
            return None

        try:
            definition = self._definition_registry.get(
                run.definition_key, run.definition_version
            )
            definition_step = definition.step_by_id(step.step_id)
            node = self._node_registry.get(definition_step.node_key)
            resolved_input = self._resolve_node_input(
                run, step, definition_step, node_input
            )
        except WorkflowDefinitionError:
            # Step 已被原子认领，配置错误也必须留下可审计的终态，不能卡在 running。
            self._fail_claimed_step(run_id, step.id, attempt.id)
            raise
        if not isinstance(resolved_input, node.input_type):
            self._fail_claimed_step(run_id, step.id, attempt.id)
            raise WorkflowDefinitionTopologyError(
                f"Node input does not match {definition_step.node_key} contract."
            )

        try:
            output = node.execute(
                resolved_input,
                WorkflowNodeExecutionContext(
                    workflow_run_id=run.id,
                    workflow_step_run_id=step.id,
                    workflow_attempt_id=attempt.id,
                    # StepRun ID 在 A1、A2… 中保持不变，外部 Service 可安全复用它去重。
                    idempotency_key=step.id,
                ),
            )
            if not isinstance(output, node.output_type) or not isinstance(output, dict):
                raise WorkflowDefinitionTopologyError(
                    f"Node {definition_step.node_key} must return its declared JSON object output."
                )
            next_step_id = self._route_resolver.select_next_step_id(
                definition_step, node_output=output
            )
        except WorkflowRetryableNodeError:
            self._fail_claimed_step(
                run_id, step.id, attempt.id, _NODE_RETRYABLE_FAILURE
            )
            logger.warning(
                "workflow_node_retryable_failure",
                extra={"run_id": run_id, "step_id": step.id},
            )
            raise
        except Exception:
            self._fail_claimed_step(
                run_id, step.id, attempt.id, _NODE_EXECUTION_FAILURE
            )
            logger.exception(
                "workflow_node_execution_failed",
                extra={"run_id": run_id, "step_id": step.id},
            )
            raise

        return self._complete_claimed_step(
            run_id, step.id, attempt, output, next_step_id
        )

    def _resolve_node_input(
        self,
        run: WorkflowRun,
        step: WorkflowStepRun,
        definition_step: WorkflowStepDefinition,
        supplied_input: object | None,
    ) -> object:
        """优先执行 Definition 映射；未声明映射时才接受调用方的明确输入。"""

        if not definition_step.input_bindings:
            if supplied_input is None:
                raise WorkflowDefinitionTopologyError(
                    "A Step without input_bindings requires supplied node_input."
                )
            return supplied_input
        if supplied_input is not None:
            raise WorkflowDefinitionTopologyError(
                "A Step with input_bindings does not accept supplied node_input."
            )
        previous_step = self._repository.get_latest_succeeded_step_before(
            run.id, step.step_index
        )
        return self._route_resolver.build_node_input(
            definition_step,
            run_input=run.run_input,
            previous_step_output=(
                previous_step.output_payload if previous_step is not None else None
            ),
        )

    def _claim_next_step(
        self, run_id: str
    ) -> tuple[WorkflowRun | None, WorkflowStepRun | None, WorkflowAttempt | None]:
        """短事务一：认领 pending Step、创建 running Attempt 并提交。"""

        run = self._repository.get_run(run_id)
        if run is None or run.status != WorkflowRunStatus.RUNNING.value:
            return None, None, None
        step = self._repository.get_next_pending_step(run_id)
        if step is None or not self._repository.claim_step(step.id):
            self._session.rollback()
            return None, None, None
        attempt = self._repository.create_attempt(
            WorkflowAttempt(
                workflow_step_run_id=step.id,
                attempt_number=self._repository.get_attempt_count(step.id) + 1,
            )
        )
        self._session.commit()
        return run, step, attempt

    def _complete_claimed_step(
        self,
        run_id: str,
        step_id: str,
        attempt: WorkflowAttempt,
        output: dict[str, object],
        next_step_id: str | None,
    ) -> StepExecutionResult:
        """短事务二成功路径：持久化输出、收口 Step，并在最后一步完成 Run。"""

        if not self._repository.complete_attempt_and_step(
            attempt_id=attempt.id, step_id=step_id, output_payload=output
        ):
            self._session.rollback()
            raise WorkflowDefinitionTopologyError(
                "Claimed workflow state changed before completion."
            )
        self._repository.complete_run_if_no_pending_steps(run_id)
        self._session.commit()
        run = self._repository.get_run(run_id)
        if run is None:
            raise WorkflowDefinitionTopologyError(
                "WorkflowRun disappeared after completion."
            )
        return StepExecutionResult(
            run_id,
            step_id,
            attempt.attempt_number,
            WorkflowRunStatus(run.status),
            output,
            next_step_id,
        )

    def _fail_claimed_step(
        self,
        run_id: str,
        step_id: str,
        attempt_id: str,
        failure_code: str = _NODE_EXECUTION_FAILURE,
    ) -> None:
        """短事务二失败路径：写入稳定失败码并提交，保留 Attempt 审计事实。"""

        if not self._repository.fail_attempt_step_and_run(
            attempt_id=attempt_id,
            step_id=step_id,
            run_id=run_id,
            failure_code=failure_code,
        ):
            self._session.rollback()
            raise WorkflowDefinitionTopologyError(
                "Claimed workflow state changed before failure persistence."
            )
        self._session.commit()
