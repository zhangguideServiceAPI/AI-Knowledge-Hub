"""Workflow Node 的类型化能力边界。"""

from typing import Protocol, TypeVar


InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


class WorkflowNode(Protocol[InputT, OutputT]):
    """由 Definition 固定选择、并由后续 Executor 调用的内部业务步骤。"""

    node_key: str
    input_type: type[InputT]
    output_type: type[OutputT]

    def execute(self, node_input: InputT) -> OutputT:
        """接收已验证的类型化输入，并返回下一 Step 可消费的类型化输出。"""

        ...
