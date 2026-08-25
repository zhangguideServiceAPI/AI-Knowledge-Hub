"""Workflow Definition 与 Node 注册阶段的稳定领域异常。"""


class WorkflowDefinitionError(ValueError):
    """所有可预期 Workflow Definition 或 Node Contract 配置错误的基类。"""


class DuplicateWorkflowNodeError(WorkflowDefinitionError):
    """两个 Node 使用同一个 node_key，导致运行时选择不确定。"""


class WorkflowNodeNotFoundError(WorkflowDefinitionError):
    """Definition 引用了尚未注册的 node_key。"""


class DuplicateWorkflowDefinitionError(WorkflowDefinitionError):
    """Registry 中存在相同 key 与 version 的两份 Definition。"""


class WorkflowDefinitionNotFoundError(WorkflowDefinitionError):
    """请求的历史 Definition key/version 没有被当前代码保留。"""


class WorkflowDefinitionTopologyError(WorkflowDefinitionError):
    """Definition 的起点、边、可达性或环路不满足顺序流程契约。"""


class WorkflowDefinitionTypeMismatchError(WorkflowDefinitionError):
    """Step 与 Node 或相邻 Step 的输入输出类型契约不一致。"""


class WorkflowInputMappingError(WorkflowDefinitionError):
    """受控字段映射缺少来源字段或违反其静态契约。"""


class WorkflowBranchResolutionError(WorkflowDefinitionError):
    """Node 输出没有匹配到 Definition 明确声明的固定分支。"""
