"""知识修订审批 Workflow 的受控生产 Definition；实际索引动作由 Story 6.8 接入。"""

from app.workflow.definition import (
    WorkflowBranchCase,
    WorkflowBranchDefinition,
    WorkflowDefinition,
    WorkflowInputBinding,
    WorkflowInputSource,
    WorkflowStepDefinition,
)
from app.workflow.node import WorkflowNodeExecutionContext
from app.workflow.registry import WorkflowDefinitionRegistry, WorkflowNodeRegistry


class WaitForApprovalNode:
    """人工等待占位 Node；审批 Service 直接迁移 waiting Step，Executor 不执行它。"""

    node_key = "wait_for_approval"
    input_type = dict
    output_type = dict

    def execute(
        self, node_input: dict[str, object], context: WorkflowNodeExecutionContext
    ) -> dict[str, object]:
        """拒绝被 Executor 直接调用，防止程序错误地伪造人工批准。"""

        del node_input, context
        raise RuntimeError("Human approval must be decided through WorkflowService.")


class IndexAndActivateVersionNode:
    """Story 6.7 的注册占位；6.8 才注入 KnowledgeService 执行索引。"""

    node_key = "index_and_activate_version"
    input_type = dict
    output_type = dict

    def execute(
        self, node_input: dict[str, object], context: WorkflowNodeExecutionContext
    ) -> dict[str, object]:
        """在真实索引 Node 接入前明确失败，禁止绕过 KnowledgeService。"""

        del node_input, context
        raise RuntimeError("Index Node is not wired before Story 6.8.")


def build_knowledge_revision_workflow_runtime(
    *, index_node: object | None = None
) -> tuple[WorkflowDefinitionRegistry, WorkflowNodeRegistry]:
    """组装审批 v1 的 Registry；6.8 可注入真实索引 Node，其他调用保持安全占位。"""

    definition = WorkflowDefinition(
        key="knowledge_revision_approval",
        version=1,
        input_type=dict,
        start_step_id="wait_for_approval",
        steps=(
            WorkflowStepDefinition(
                "wait_for_approval",
                "wait_for_approval",
                dict,
                branch=WorkflowBranchDefinition(
                    "decision",
                    (WorkflowBranchCase("approved", "index_and_activate_version"),),
                ),
            ),
            WorkflowStepDefinition(
                "index_and_activate_version",
                "index_and_activate_version",
                dict,
                input_bindings=(
                    WorkflowInputBinding(
                        "owner_id", WorkflowInputSource.RUN_INPUT, "owner_id"
                    ),
                    WorkflowInputBinding(
                        "document_id", WorkflowInputSource.RUN_INPUT, "document_id"
                    ),
                    WorkflowInputBinding(
                        "document_version_id",
                        WorkflowInputSource.RUN_INPUT,
                        "document_version_id",
                    ),
                ),
            ),
        ),
    )
    node_registry = WorkflowNodeRegistry(
        (WaitForApprovalNode(), index_node or IndexAndActivateVersionNode())  # type: ignore[arg-type]
    )
    return WorkflowDefinitionRegistry(node_registry, (definition,)), node_registry


def build_knowledge_revision_definition_registry() -> WorkflowDefinitionRegistry:
    """为仅需审批状态迁移的调用方提供安全占位 Node 版本的 Definition Registry。"""

    definition_registry, _node_registry = build_knowledge_revision_workflow_runtime()
    return definition_registry
