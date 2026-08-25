from dataclasses import dataclass

import pytest

from app.workflow.definition import WorkflowDefinition, WorkflowStepDefinition
from app.workflow.exceptions import (
    DuplicateWorkflowDefinitionError,
    DuplicateWorkflowNodeError,
    WorkflowDefinitionNotFoundError,
    WorkflowDefinitionTopologyError,
    WorkflowDefinitionTypeMismatchError,
    WorkflowNodeNotFoundError,
)
from app.workflow.registry import WorkflowDefinitionRegistry, WorkflowNodeRegistry


@dataclass(frozen=True)
class RevisionInput:
    """模拟提交知识修订后交给审批 Step 的受控输入。"""

    document_version_id: str


@dataclass(frozen=True)
class ApprovalDecision:
    """模拟审批节点产出的、可传给下游 Index Step 的结构化决定。"""

    approved: bool


@dataclass(frozen=True)
class IndexResult:
    """模拟索引节点返回的安全结果摘要。"""

    document_version_id: str


@dataclass(frozen=True)
class DifferentInput:
    """专门用于证明相邻 Node 类型不兼容的测试 DTO。"""

    value: str


class FakeNode:
    """只声明 Node Contract 的测试替身；Registry 验证时不应调用 execute。"""

    def __init__(
        self,
        node_key: str,
        input_type: type[object],
        output_type: type[object],
    ) -> None:
        """保存测试节点的稳定 key 与输入输出类型，并记录是否被错误执行。"""

        self.node_key = node_key
        self.input_type = input_type
        self.output_type = output_type
        self.executed = False

    def execute(self, node_input: object) -> object:
        """模拟后续 Executor 才会调用的动作；当前只记录调用，不产生业务副作用。"""

        self.executed = True
        return node_input


def _node_registry(*nodes: FakeNode) -> WorkflowNodeRegistry:
    """用给定的测试 Node 组装启动期 Node Registry。"""

    return WorkflowNodeRegistry(nodes)


def _approval_definition(
    *,
    version: int = 1,
    steps: tuple[WorkflowStepDefinition, ...] | None = None,
    input_type: type[object] = RevisionInput,
    start_step_id: str = "wait_for_approval",
) -> WorkflowDefinition:
    """构造贯穿案例使用的审批后索引线性 Definition。"""

    return WorkflowDefinition(
        key="knowledge_revision_approval",
        version=version,
        input_type=input_type,
        start_step_id=start_step_id,
        steps=steps
        or (
            WorkflowStepDefinition(
                step_id="wait_for_approval",
                node_key="wait_for_approval",
                input_type=RevisionInput,
                next_step_id="index_and_activate_version",
            ),
            WorkflowStepDefinition(
                step_id="index_and_activate_version",
                node_key="index_and_activate_version",
                input_type=ApprovalDecision,
            ),
        ),
    )


def _approval_nodes() -> tuple[FakeNode, FakeNode]:
    """构造与审批 Definition 精确匹配、但不会产生外部调用的两个 Node。"""

    return (
        FakeNode("wait_for_approval", RevisionInput, ApprovalDecision),
        FakeNode("index_and_activate_version", ApprovalDecision, IndexResult),
    )


def test_definition_registry_returns_exact_immutable_version() -> None:
    nodes = _approval_nodes()
    first = _approval_definition(version=1)
    second = _approval_definition(version=2)

    registry = WorkflowDefinitionRegistry(_node_registry(*nodes), (first, second))

    assert registry.get("knowledge_revision_approval", 1) is first
    assert registry.get("knowledge_revision_approval", 2) is second
    assert all(node.executed is False for node in nodes)


def test_definition_registry_rejects_missing_definition_version() -> None:
    registry = WorkflowDefinitionRegistry(_node_registry(*_approval_nodes()), ())

    with pytest.raises(WorkflowDefinitionNotFoundError):
        registry.get("knowledge_revision_approval", 1)


def test_node_registry_rejects_duplicate_node_key() -> None:
    with pytest.raises(DuplicateWorkflowNodeError):
        _node_registry(
            FakeNode("wait_for_approval", RevisionInput, ApprovalDecision),
            FakeNode("wait_for_approval", RevisionInput, ApprovalDecision),
        )


def test_definition_registry_rejects_duplicate_key_and_version() -> None:
    definition = _approval_definition()

    with pytest.raises(DuplicateWorkflowDefinitionError):
        WorkflowDefinitionRegistry(
            _node_registry(*_approval_nodes()),
            (definition, definition),
        )


def test_definition_registry_rejects_step_that_references_missing_node() -> None:
    definition = _approval_definition(
        steps=(
            WorkflowStepDefinition(
                step_id="wait_for_approval",
                node_key="missing_node",
                input_type=RevisionInput,
            ),
        )
    )

    with pytest.raises(WorkflowNodeNotFoundError):
        WorkflowDefinitionRegistry(_node_registry(), (definition,))


def test_definition_rejects_duplicate_step_id_before_registry() -> None:
    step = WorkflowStepDefinition(
        step_id="wait_for_approval",
        node_key="wait_for_approval",
        input_type=RevisionInput,
    )

    with pytest.raises(WorkflowDefinitionTopologyError, match="duplicate step_id"):
        _approval_definition(steps=(step, step))


def test_definition_registry_rejects_unknown_next_step_id() -> None:
    definition = _approval_definition(
        steps=(
            WorkflowStepDefinition(
                step_id="wait_for_approval",
                node_key="wait_for_approval",
                input_type=RevisionInput,
                next_step_id="missing_step",
            ),
        )
    )

    with pytest.raises(WorkflowDefinitionTopologyError, match="unknown next_step_id"):
        WorkflowDefinitionRegistry(_node_registry(*_approval_nodes()), (definition,))


def test_definition_registry_rejects_cycle() -> None:
    first = FakeNode("first", RevisionInput, RevisionInput)
    second = FakeNode("second", RevisionInput, RevisionInput)
    definition = _approval_definition(
        start_step_id="first",
        steps=(
            WorkflowStepDefinition("first", "first", RevisionInput, "second"),
            WorkflowStepDefinition("second", "second", RevisionInput, "first"),
        ),
    )

    with pytest.raises(WorkflowDefinitionTopologyError, match="cycle"):
        WorkflowDefinitionRegistry(_node_registry(first, second), (definition,))


def test_definition_registry_rejects_unreachable_step() -> None:
    first = FakeNode("first", RevisionInput, RevisionInput)
    detached = FakeNode("detached", RevisionInput, IndexResult)
    definition = _approval_definition(
        start_step_id="first",
        steps=(
            WorkflowStepDefinition("first", "first", RevisionInput),
            WorkflowStepDefinition("detached", "detached", RevisionInput),
        ),
    )

    with pytest.raises(WorkflowDefinitionTopologyError, match="unreachable"):
        WorkflowDefinitionRegistry(_node_registry(first, detached), (definition,))


def test_definition_registry_rejects_multiple_predecessors() -> None:
    first = FakeNode("first", RevisionInput, RevisionInput)
    second = FakeNode("second", RevisionInput, RevisionInput)
    target = FakeNode("target", RevisionInput, IndexResult)
    definition = _approval_definition(
        start_step_id="first",
        steps=(
            WorkflowStepDefinition("first", "first", RevisionInput, "target"),
            WorkflowStepDefinition("second", "second", RevisionInput, "target"),
            WorkflowStepDefinition("target", "target", RevisionInput),
        ),
    )

    with pytest.raises(WorkflowDefinitionTopologyError, match="multiple predecessors"):
        WorkflowDefinitionRegistry(_node_registry(first, second, target), (definition,))


def test_definition_registry_rejects_step_node_input_type_mismatch() -> None:
    definition = _approval_definition(
        steps=(
            WorkflowStepDefinition(
                step_id="wait_for_approval",
                node_key="wait_for_approval",
                input_type=DifferentInput,
            ),
        )
    )

    with pytest.raises(
        WorkflowDefinitionTypeMismatchError, match="does not match Node"
    ):
        WorkflowDefinitionRegistry(_node_registry(*_approval_nodes()), (definition,))


def test_definition_registry_rejects_edge_output_input_type_mismatch() -> None:
    first = FakeNode("first", RevisionInput, ApprovalDecision)
    second = FakeNode("second", DifferentInput, IndexResult)
    definition = _approval_definition(
        start_step_id="first",
        steps=(
            WorkflowStepDefinition("first", "first", RevisionInput, "second"),
            WorkflowStepDefinition("second", "second", DifferentInput),
        ),
    )

    with pytest.raises(
        WorkflowDefinitionTypeMismatchError, match="does not match next Node"
    ):
        WorkflowDefinitionRegistry(_node_registry(first, second), (definition,))


def test_definition_registry_rejects_definition_start_input_type_mismatch() -> None:
    definition = _approval_definition(input_type=DifferentInput)

    with pytest.raises(
        WorkflowDefinitionTypeMismatchError, match="Definition input type"
    ):
        WorkflowDefinitionRegistry(_node_registry(*_approval_nodes()), (definition,))
