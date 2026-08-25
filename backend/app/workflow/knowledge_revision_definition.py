"""知识修订审批 Workflow 的受控生产 Definition；实际索引动作由 Story 6.8 接入。"""

from app.workflow.definition import (
    WorkflowBranchCase,
    WorkflowBranchDefinition,
    WorkflowDefinition,
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


def build_knowledge_revision_definition_registry() -> WorkflowDefinitionRegistry:
    """创建审批 v1 的不可变 Registry，供 API 与 Service 精确绑定历史 Definition。"""

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
                "index_and_activate_version", "index_and_activate_version", dict
            ),
        ),
    )
    node_registry = WorkflowNodeRegistry(
        (WaitForApprovalNode(), IndexAndActivateVersionNode())
    )
    return WorkflowDefinitionRegistry(node_registry, (definition,))
