"""Story 6.8 索引 Node 必须通过 KnowledgeService 的边界测试。"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.models.document_version import DocumentVersion, DocumentVersionStatus
from app.workflow.exceptions import WorkflowRetryableNodeError
from app.workflow.knowledge_nodes import IndexAndActivateVersionNode
from app.workflow.node import WorkflowNodeExecutionContext


def test_index_node_delegates_to_knowledge_service() -> None:
    knowledge_service = AsyncMock()
    knowledge_service.index_document_version.return_value = DocumentVersion(
        id="version-1",
        document_id="document-1",
        version_number=1,
        processing_fingerprint="f" * 64,
        parser_name="plain",
        parser_version="1",
        chunker_name="chunker",
        chunker_config={},
        embedding_profile="test",
        embedding_dimension=3,
        status=DocumentVersionStatus.INDEXED.value,
    )
    components = object()
    node = IndexAndActivateVersionNode(knowledge_service, components)  # type: ignore[arg-type]

    result = asyncio.run(
        node.execute(
            {
                "owner_id": 1,
                "document_id": "document-1",
                "document_version_id": "version-1",
            },
            WorkflowNodeExecutionContext("run-1", "step-1", "attempt-1", "step-1"),
        )
    )

    assert result == {"document_version_id": "version-1", "index_status": "indexed"}
    knowledge_service.index_document_version.assert_awaited_once()


def test_index_node_keeps_non_indexed_version_retryable() -> None:
    """KnowledgeService 已写入技术失败时，Node 不把 Workflow 误收口为成功。"""

    knowledge_service = AsyncMock()
    knowledge_service.index_document_version.return_value = DocumentVersion(
        id="version-1",
        document_id="document-1",
        version_number=1,
        processing_fingerprint="f" * 64,
        parser_name="plain",
        parser_version="1",
        chunker_name="chunker",
        chunker_config={},
        embedding_profile="test",
        embedding_dimension=3,
        status=DocumentVersionStatus.CLEANUP_REQUIRED.value,
    )
    node = IndexAndActivateVersionNode(knowledge_service, object())  # type: ignore[arg-type]

    with pytest.raises(WorkflowRetryableNodeError, match="cleanup_required"):
        asyncio.run(
            node.execute(
                {
                    "owner_id": 1,
                    "document_id": "document-1",
                    "document_version_id": "version-1",
                },
                WorkflowNodeExecutionContext("run-1", "step-1", "attempt-1", "step-1"),
            )
        )
