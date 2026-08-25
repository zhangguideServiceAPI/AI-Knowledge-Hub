"""Story 6.4 受控字段映射和固定分支的纯领域测试。"""

import pytest

from app.workflow.definition import (
    WorkflowBranchCase,
    WorkflowBranchDefinition,
    WorkflowDefinition,
    WorkflowInputBinding,
    WorkflowInputSource,
    WorkflowStepDefinition,
)
from app.workflow.exceptions import (
    WorkflowBranchResolutionError,
    WorkflowDefinitionTopologyError,
    WorkflowInputMappingError,
)
from app.workflow.registry import WorkflowDefinitionRegistry, WorkflowNodeRegistry
from app.workflow.routing import WorkflowRouteResolver


class DictNode:
    """只声明 dict 输入输出契约的测试 Node，Registry 不会执行它。"""

    input_type = dict
    output_type = dict

    def __init__(self, node_key: str) -> None:
        """保存该测试 Node 的稳定注册 key。"""

        self.node_key = node_key

    def execute(self, node_input: dict[str, object]) -> dict[str, object]:
        """返回输入以满足 Protocol；本 Story 测试不应调用它。"""

        return node_input


def _approval_branch_step() -> WorkflowStepDefinition:
    """构造审批输出按 decision 进入固定 approved/rejected Step 的定义。"""

    return WorkflowStepDefinition(
        step_id="approval",
        node_key="approval",
        input_type=dict,
        branch=WorkflowBranchDefinition(
            selector_field="decision",
            cases=(
                WorkflowBranchCase("approved", "index"),
                WorkflowBranchCase("rejected", "record_rejection"),
            ),
        ),
    )


def test_route_resolver_maps_run_and_previous_output_fields() -> None:
    resolver = WorkflowRouteResolver()
    step = WorkflowStepDefinition(
        step_id="index",
        node_key="index",
        input_type=dict,
        input_bindings=(
            WorkflowInputBinding(
                "document_version_id", WorkflowInputSource.RUN_INPUT, "version_id"
            ),
            WorkflowInputBinding(
                "approved_by", WorkflowInputSource.PREVIOUS_STEP_OUTPUT, "reviewer_id"
            ),
        ),
    )

    node_input = resolver.build_node_input(
        step,
        run_input={"version_id": "v1", "unrelated": "ignored"},
        previous_step_output={"reviewer_id": 7, "decision": "approved"},
    )

    assert node_input == {"document_version_id": "v1", "approved_by": 7}


def test_route_resolver_rejects_missing_mapped_field() -> None:
    step = WorkflowStepDefinition(
        step_id="index",
        node_key="index",
        input_type=dict,
        input_bindings=(
            WorkflowInputBinding(
                "document_version_id", WorkflowInputSource.RUN_INPUT, "version_id"
            ),
        ),
    )

    with pytest.raises(WorkflowInputMappingError, match="Missing run_input field"):
        WorkflowRouteResolver().build_node_input(
            step, run_input={}, previous_step_output=None
        )


def test_route_resolver_selects_only_definition_declared_branch() -> None:
    resolver = WorkflowRouteResolver()
    step = _approval_branch_step()

    assert (
        resolver.select_next_step_id(step, node_output={"decision": "approved"})
        == "index"
    )
    assert (
        resolver.select_next_step_id(step, node_output={"decision": "rejected"})
        == "record_rejection"
    )


def test_route_resolver_rejects_missing_or_unknown_branch_decision() -> None:
    resolver = WorkflowRouteResolver()
    step = _approval_branch_step()

    with pytest.raises(WorkflowBranchResolutionError, match="Missing branch selector"):
        resolver.select_next_step_id(step, node_output={})
    with pytest.raises(WorkflowBranchResolutionError, match="Unsupported branch value"):
        resolver.select_next_step_id(step, node_output={"decision": "skip_approval"})


def test_step_rejects_linear_and_branch_successor_together() -> None:
    with pytest.raises(
        WorkflowDefinitionTopologyError, match="both next_step_id and branch"
    ):
        WorkflowStepDefinition(
            step_id="approval",
            node_key="approval",
            input_type=dict,
            next_step_id="index",
            branch=WorkflowBranchDefinition(
                "decision", (WorkflowBranchCase("approved", "index"),)
            ),
        )


def test_registry_validates_all_fixed_branch_edges() -> None:
    definition = WorkflowDefinition(
        key="approval_branch",
        version=1,
        input_type=dict,
        start_step_id="approval",
        steps=(
            _approval_branch_step(),
            WorkflowStepDefinition("index", "index", dict),
            WorkflowStepDefinition("record_rejection", "record_rejection", dict),
        ),
    )

    WorkflowDefinitionRegistry(
        WorkflowNodeRegistry(
            (DictNode("approval"), DictNode("index"), DictNode("record_rejection"))
        ),
        (definition,),
    )
