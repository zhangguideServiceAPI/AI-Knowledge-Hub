"""Workflow Node 的类型化能力边界。"""

from dataclasses import dataclass
from typing import Protocol, TypeVar


InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


@dataclass(frozen=True)
class WorkflowNodeExecutionContext:
    """Executor 传给 Node 的持久化执行身份与跨 Attempt 稳定幂等键。"""

    workflow_run_id: str
    workflow_step_run_id: str
    workflow_attempt_id: str
    idempotency_key: str


class WorkflowNode(Protocol[InputT, OutputT]):
    """由 Definition 固定选择、并由后续 Executor 调用的内部业务步骤。"""

    node_key: str
    input_type: type[InputT]
    output_type: type[OutputT]

    def execute(
        self, node_input: InputT, context: WorkflowNodeExecutionContext
    ) -> OutputT:
        """接收输入及幂等上下文，返回下一 Step 可消费的结构化输出。"""

        ...
