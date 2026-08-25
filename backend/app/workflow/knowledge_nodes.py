"""知识修订 Workflow 的业务 Node；只经 KnowledgeService 访问索引能力。"""

from dataclasses import dataclass

from app.models.document_version import DocumentVersionStatus
from app.services.knowledge_service import KnowledgeIndexingComponents, KnowledgeService
from app.workflow.exceptions import WorkflowRetryableNodeError
from app.workflow.node import WorkflowNodeExecutionContext


@dataclass(frozen=True)
class IndexAndActivateVersionInput:
    """审批通过后索引 Version 所需的最小安全标识快照。"""

    owner_id: int
    document_id: str
    document_version_id: str


class IndexAndActivateVersionNode:
    """调用 KnowledgeService 完成 Version 索引与 active 指针提升的异步业务 Node。"""

    node_key = "index_and_activate_version"
    input_type = dict
    output_type = dict

    def __init__(
        self,
        knowledge_service: KnowledgeService,
        components: KnowledgeIndexingComponents,
    ) -> None:
        """注入应用 Service 与服务器索引组件，不保存 Qdrant/Provider SDK。"""

        self._knowledge_service = knowledge_service
        self._components = components

    async def execute(
        self,
        node_input: dict[str, object],
        context: WorkflowNodeExecutionContext,
    ) -> dict[str, object]:
        """执行幂等的 Version 索引；未认领代表其他执行者已处理，作为可恢复冲突失败。"""

        del context
        try:
            index_input = IndexAndActivateVersionInput(
                owner_id=int(node_input["owner_id"]),
                document_id=str(node_input["document_id"]),
                document_version_id=str(node_input["document_version_id"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Index Node input is incomplete or invalid.") from error
        version = await self._knowledge_service.index_document_version(
            owner_id=index_input.owner_id,
            document_id=index_input.document_id,
            document_version_id=index_input.document_version_id,
            components=self._components,
        )
        if version is None:
            raise WorkflowRetryableNodeError("document_version_not_claimed")
        if version.status != DocumentVersionStatus.INDEXED.value:
            # KnowledgeService 已把技术失败事实写入 Version；Workflow 只记录可恢复的
            # 编排失败，不能把 failed/cleanup_required 伪装成已发布成功。
            raise WorkflowRetryableNodeError(
                f"document_version_not_indexed:{version.status}"
            )
        return {
            "document_version_id": version.id,
            "index_status": version.status,
        }
