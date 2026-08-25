"""Workflow Node 与不可变 Definition 的启动期注册和校验。"""

from collections.abc import Iterable, Mapping
from types import MappingProxyType

from app.workflow.definition import (
    WorkflowDefinition,
    WorkflowInputSource,
    WorkflowStepDefinition,
)
from app.workflow.exceptions import (
    DuplicateWorkflowDefinitionError,
    DuplicateWorkflowNodeError,
    WorkflowDefinitionNotFoundError,
    WorkflowDefinitionTopologyError,
    WorkflowDefinitionTypeMismatchError,
    WorkflowNodeNotFoundError,
)
from app.workflow.node import WorkflowNode


def _type_name(value: type[object]) -> str:
    """生成稳定、可读的类型名称，用于启动期配置错误而不泄露业务输入。"""

    return value.__name__


class WorkflowNodeRegistry:
    """按 node_key 保存唯一 Node，并拒绝运行时不确定的重复注册。"""

    def __init__(self, nodes: Iterable[WorkflowNode[object, object]]) -> None:
        """一次性组装只读 Node 表；不会调用任何 Node 的 execute()。"""

        registered_nodes: dict[str, WorkflowNode[object, object]] = {}
        for node in nodes:
            if not node.node_key.strip():
                raise WorkflowDefinitionTopologyError(
                    "Node node_key must not be empty."
                )
            if not isinstance(node.input_type, type):
                raise WorkflowDefinitionTopologyError(
                    f"Node {node.node_key} input_type must be a runtime type."
                )
            if not isinstance(node.output_type, type):
                raise WorkflowDefinitionTopologyError(
                    f"Node {node.node_key} output_type must be a runtime type."
                )
            if node.node_key in registered_nodes:
                raise DuplicateWorkflowNodeError(
                    f"Multiple Workflow Nodes use node_key: {node.node_key}."
                )
            registered_nodes[node.node_key] = node

        # MappingProxyType 只读包装启动时完成的 dict，避免应用运行后覆盖 Node。
        self._nodes: Mapping[str, WorkflowNode[object, object]] = MappingProxyType(
            registered_nodes
        )

    def get(self, node_key: str) -> WorkflowNode[object, object]:
        """按 key 返回已注册 Node；缺失时抛出可定位的领域异常。"""

        try:
            return self._nodes[node_key]
        except KeyError as error:
            raise WorkflowNodeNotFoundError(
                f"Workflow Node is not registered: {node_key}."
            ) from error


class WorkflowDefinitionRegistry:
    """保存并验证全部代码型 Definition，使错误流程无法创建 WorkflowRun。"""

    def __init__(
        self,
        node_registry: WorkflowNodeRegistry,
        definitions: Iterable[WorkflowDefinition],
    ) -> None:
        """校验并一次性注册所有 Definition，随后冻结其 key/version 查找表。"""

        registered_definitions: dict[tuple[str, int], WorkflowDefinition] = {}
        for definition in definitions:
            definition_key = (definition.key, definition.version)
            if definition_key in registered_definitions:
                raise DuplicateWorkflowDefinitionError(
                    "Multiple Workflow Definitions use "
                    f"key/version: {definition.key}@{definition.version}."
                )
            self._validate_definition(node_registry, definition)
            registered_definitions[definition_key] = definition

        self._definitions: Mapping[tuple[str, int], WorkflowDefinition] = (
            MappingProxyType(registered_definitions)
        )

    def get(self, key: str, version: int) -> WorkflowDefinition:
        """按精确 key/version 读取历史 Definition，绝不自动回退到其他版本。"""

        try:
            return self._definitions[(key, version)]
        except KeyError as error:
            raise WorkflowDefinitionNotFoundError(
                f"Workflow Definition is not registered: {key}@{version}."
            ) from error

    @staticmethod
    def _validate_definition(
        node_registry: WorkflowNodeRegistry,
        definition: WorkflowDefinition,
    ) -> None:
        """在创建任何 Run 前校验 Node、边、顺序拓扑与相邻步骤类型。"""

        steps_by_id = {step.step_id: step for step in definition.steps}
        incoming_edges = {step.step_id: 0 for step in definition.steps}

        for step in definition.steps:
            node = node_registry.get(step.node_key)
            if node.input_type is not step.input_type:
                raise WorkflowDefinitionTypeMismatchError(
                    f"Step {step.step_id} input type {_type_name(step.input_type)} "
                    f"does not match Node {step.node_key} input type "
                    f"{_type_name(node.input_type)}."
                )

            if step.input_bindings and step.input_type is not dict:
                raise WorkflowDefinitionTypeMismatchError(
                    f"Step {step.step_id} uses input_bindings but does not accept dict input."
                )
            if step.step_id == definition.start_step_id and any(
                binding.source is WorkflowInputSource.PREVIOUS_STEP_OUTPUT
                for binding in step.input_bindings
            ):
                raise WorkflowDefinitionTopologyError(
                    "The start Step cannot read previous_step_output."
                )

            for next_step_id in step.outgoing_step_ids:
                next_step = steps_by_id.get(next_step_id)
                if next_step is None:
                    raise WorkflowDefinitionTopologyError(
                        f"Step {step.step_id} references unknown next_step_id: "
                        f"{next_step_id}."
                    )
                incoming_edges[next_step.step_id] += 1
                if incoming_edges[next_step.step_id] > 1:
                    raise WorkflowDefinitionTopologyError(
                        "Workflow Definition cannot have multiple predecessors for "
                        f"step_id: {next_step.step_id}."
                    )

                next_node = node_registry.get(next_step.node_key)
                if node.output_type is not next_node.input_type:
                    raise WorkflowDefinitionTypeMismatchError(
                        f"Node {step.node_key} output type {_type_name(node.output_type)} "
                        f"does not match next Node {next_step.node_key} input type "
                        f"{_type_name(next_node.input_type)}."
                    )

        start_step = steps_by_id[definition.start_step_id]
        if definition.input_type is not start_step.input_type:
            raise WorkflowDefinitionTypeMismatchError(
                f"Definition input type {_type_name(definition.input_type)} does not "
                f"match start Step {start_step.step_id} input type "
                f"{_type_name(start_step.input_type)}."
            )

        reachable_step_ids: set[str] = set()
        visiting_step_ids: set[str] = set()

        def visit(step: WorkflowStepDefinition) -> None:
            """深度优先遍历线性边，同时识别环路与记录从起点可达的 Step。"""

            if step.step_id in visiting_step_ids:
                raise WorkflowDefinitionTopologyError(
                    f"Workflow Definition contains a cycle at step_id: {step.step_id}."
                )
            if step.step_id in reachable_step_ids:
                return

            visiting_step_ids.add(step.step_id)
            for next_step_id in step.outgoing_step_ids:
                visit(steps_by_id[next_step_id])
            visiting_step_ids.remove(step.step_id)
            reachable_step_ids.add(step.step_id)

        visit(start_step)
        unreachable_step_ids = set(steps_by_id) - reachable_step_ids
        if unreachable_step_ids:
            raise WorkflowDefinitionTopologyError(
                "Workflow Definition contains unreachable steps: "
                f"{', '.join(sorted(unreachable_step_ids))}."
            )
