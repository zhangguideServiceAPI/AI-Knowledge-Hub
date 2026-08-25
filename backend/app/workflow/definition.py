"""代码型、不可变的 Workflow Definition 数据契约。"""

from dataclasses import dataclass
from enum import StrEnum

from app.workflow.exceptions import WorkflowDefinitionTopologyError


def _require_non_empty(value: str, field_name: str) -> None:
    """拒绝空白标识，避免 Registry 把无意义字符串当作稳定业务 key。"""

    if not value.strip():
        raise WorkflowDefinitionTopologyError(f"{field_name} must not be empty.")


def _require_runtime_type(value: object, field_name: str) -> None:
    """确认契约字段是可在运行时比较身份的 Python class，而非任意对象。"""

    if not isinstance(value, type):
        raise WorkflowDefinitionTopologyError(f"{field_name} must be a runtime type.")


class WorkflowInputSource(StrEnum):
    """字段映射允许读取的两个受控数据来源。"""

    RUN_INPUT = "run_input"
    PREVIOUS_STEP_OUTPUT = "previous_step_output"


@dataclass(frozen=True)
class WorkflowInputBinding:
    """把一个允许来源的顶层字段复制到 Node 输入的指定字段。"""

    target_field: str
    source: WorkflowInputSource
    source_field: str

    def __post_init__(self) -> None:
        """拒绝空字段名与未声明来源，避免运行时读取任意对象路径。"""

        _require_non_empty(self.target_field, "target_field")
        _require_non_empty(self.source_field, "source_field")
        if not isinstance(self.source, WorkflowInputSource):
            raise WorkflowDefinitionTopologyError(
                "source must be a WorkflowInputSource."
            )


@dataclass(frozen=True)
class WorkflowBranchCase:
    """一个固定 selector 值对应的唯一后继 Step。"""

    expected_value: str
    next_step_id: str

    def __post_init__(self) -> None:
        """在 Definition 创建时限制分支值与目标均为稳定非空标识。"""

        _require_non_empty(self.expected_value, "expected_value")
        _require_non_empty(self.next_step_id, "next_step_id")


@dataclass(frozen=True)
class WorkflowBranchDefinition:
    """从 Node JSON 输出的一个字段按精确值选择固定后继 Step。"""

    selector_field: str
    cases: tuple[WorkflowBranchCase, ...]

    def __post_init__(self) -> None:
        """确保一个 selector 至少有一条且没有重复的受控分支值。"""

        _require_non_empty(self.selector_field, "selector_field")
        if not self.cases:
            raise WorkflowDefinitionTopologyError("branch cases must not be empty.")
        expected_values = tuple(case.expected_value for case in self.cases)
        if len(set(expected_values)) != len(expected_values):
            raise WorkflowDefinitionTopologyError(
                "branch cases contain duplicate expected_value values."
            )


@dataclass(frozen=True)
class WorkflowStepDefinition:
    """Definition 中一个固定 Step 的 Node、输入映射和固定后继规则。"""

    step_id: str
    node_key: str
    input_type: type[object]
    next_step_id: str | None = None
    input_bindings: tuple[WorkflowInputBinding, ...] = ()
    branch: WorkflowBranchDefinition | None = None
    max_attempts: int = 3

    def __post_init__(self) -> None:
        """在冻结 Step 创建时校验其最小静态契约。"""

        _require_non_empty(self.step_id, "step_id")
        _require_non_empty(self.node_key, "node_key")
        _require_runtime_type(self.input_type, "input_type")
        if self.next_step_id is not None:
            _require_non_empty(self.next_step_id, "next_step_id")
        if self.next_step_id is not None and self.branch is not None:
            raise WorkflowDefinitionTopologyError(
                "Step cannot define both next_step_id and branch."
            )
        target_fields = tuple(binding.target_field for binding in self.input_bindings)
        if len(set(target_fields)) != len(target_fields):
            raise WorkflowDefinitionTopologyError(
                "input_bindings contain duplicate target_field values."
            )
        if self.max_attempts <= 0:
            raise WorkflowDefinitionTopologyError("max_attempts must be positive.")

    @property
    def outgoing_step_ids(self) -> tuple[str, ...]:
        """返回线性后继或固定分支的全部候选后继，供 Registry 校验拓扑。"""

        if self.branch is not None:
            return tuple(case.next_step_id for case in self.branch.cases)
        if self.next_step_id is not None:
            return (self.next_step_id,)
        return ()


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
