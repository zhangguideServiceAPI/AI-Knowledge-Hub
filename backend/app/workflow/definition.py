"""代码型、不可变的 Workflow Definition 数据契约。"""

from dataclasses import dataclass

from app.workflow.exceptions import WorkflowDefinitionTopologyError


def _require_non_empty(value: str, field_name: str) -> None:
    """拒绝空白标识，避免 Registry 把无意义字符串当作稳定业务 key。"""

    if not value.strip():
        raise WorkflowDefinitionTopologyError(f"{field_name} must not be empty.")


def _require_runtime_type(value: object, field_name: str) -> None:
    """确认契约字段是可在运行时比较身份的 Python class，而非任意对象。"""

    if not isinstance(value, type):
        raise WorkflowDefinitionTopologyError(f"{field_name} must be a runtime type.")


@dataclass(frozen=True)
class WorkflowStepDefinition:
    """Definition 中一个固定 Step 的标识、Node 选择、输入类型与线性后继。"""

    step_id: str
    node_key: str
    input_type: type[object]
    next_step_id: str | None = None

    def __post_init__(self) -> None:
        """在冻结 Step 创建时校验其最小静态契约。"""

        _require_non_empty(self.step_id, "step_id")
        _require_non_empty(self.node_key, "node_key")
        _require_runtime_type(self.input_type, "input_type")
        if self.next_step_id is not None:
            _require_non_empty(self.next_step_id, "next_step_id")


@dataclass(frozen=True)
class WorkflowDefinition:
    """一个由服务端代码维护、带版本且不可变的线性 Workflow 说明书。"""

    key: str
    version: int
    input_type: type[object]
    start_step_id: str
    steps: tuple[WorkflowStepDefinition, ...]

    def __post_init__(self) -> None:
        """校验无需 Node Registry 即可确认的 key、版本、起点与重复 Step。"""

        _require_non_empty(self.key, "key")
        if self.version <= 0:
            raise WorkflowDefinitionTopologyError("version must be positive.")
        _require_runtime_type(self.input_type, "input_type")
        _require_non_empty(self.start_step_id, "start_step_id")
        if not self.steps:
            raise WorkflowDefinitionTopologyError(
                "Definition must contain at least one step."
            )

        step_ids = tuple(step.step_id for step in self.steps)
        if len(set(step_ids)) != len(step_ids):
            raise WorkflowDefinitionTopologyError(
                "Definition contains duplicate step_id values."
            )
        if self.start_step_id not in step_ids:
            raise WorkflowDefinitionTopologyError(
                "start_step_id must reference a Definition step."
            )

    def step_by_id(self, step_id: str) -> WorkflowStepDefinition:
        """取得稳定 Step 标识对应的 Definition；缺失时返回明确配置错误。"""

        for step in self.steps:
            if step.step_id == step_id:
                return step
        raise WorkflowDefinitionTopologyError(
            f"Definition does not contain step_id: {step_id}."
        )
