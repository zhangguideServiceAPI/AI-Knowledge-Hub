"""Knowledge 域依赖的向量存储能力边界。"""

from dataclasses import dataclass
from typing import Protocol

from app.knowledge.retrieval import VectorSearchCandidate


@dataclass(frozen=True)
class VectorPoint:
    """
    写入向量库的一个 Chunk 向量点及最小检索元数据。

    输入来自已持久化的 DocumentChunk 和 EmbeddingGateway；`chunk_id` 是点的稳定
    标识，`knowledge_base_id` 用于检索范围过滤，`document_version_id` 用于失败补偿。
    原文、文件路径和权限关系仍只保存在 MySQL，不复制为向量库的业务真相。
    """

    chunk_id: str
    vector: tuple[float, ...]
    knowledge_base_id: str
    document_version_id: str


class VectorStore(Protocol):
    """
    Service 使用的最小向量存储能力，不暴露 Qdrant SDK 类型。

    具体实现负责将 VectorPoint 转换为其数据库的写入格式；Service 仅依赖本协议，
    因而未来可替换 Qdrant 或使用内存 Fake，而不改变索引业务流程。
    """

    async def upsert(self, *, points: tuple[VectorPoint, ...]) -> None:
        """
        新建或覆盖一批以 `chunk_id` 为稳定标识的向量点。

        输入是同一索引流程产生的 VectorPoint；成功时没有返回值。
        向量库超时、不可用或拒绝写入时抛出实现定义的异常，由 Service 决定状态和补偿。
        """

        ...

    async def delete_by_document_version(self, *, document_version_id: str) -> None:
        """
        删除一个 DocumentVersion 在向量库中已写入的全部向量点。

        输入是失败或删除流程确定的 Version ID；成功时没有返回值。
        删除失败必须向上抛出，以便 Service 标记 `cleanup_required` 而非错误声称清理完成。
        """

        ...

    async def search(
        self,
        *,
        query_vector: tuple[float, ...],
        knowledge_base_id: str,
        limit: int,
        score_threshold: float,
    ) -> tuple[VectorSearchCandidate, ...]:
        """
        在一个 KnowledgeBase 范围内查询相似向量候选。

        返回只包含 Chunk ID 和相似度分数的有序候选，不返回原文或权限结论。调用方必须
        用 MySQL 确认 Chunk 仍属于当前 active Version；Collection 不存在时应返回空 tuple，
        而不是为了查询创建一个新的 Collection。
        """

        ...
