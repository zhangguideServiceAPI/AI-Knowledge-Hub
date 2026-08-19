"""Knowledge 检索阶段在 Service、VectorStore 和 Repository 间传递的稳定数据。"""

import math
from dataclasses import dataclass

from app.knowledge.parsing import SourceLocator


@dataclass(frozen=True)
class VectorSearchCandidate:
    """
    VectorStore 返回的一个候选 Chunk ID 与相似度分数。

    它不包含原文、权限或来源；Service 必须通过 MySQL 将候选校验为当前有效 Chunk 后，
    才能产生对外可用的 RetrievalHit。
    """

    chunk_id: str
    score: float

    def __post_init__(self) -> None:
        """拒绝空 Point ID 和非有限分数，避免无效候选进入 MySQL 回填步骤。"""

        if not self.chunk_id.strip() or not math.isfinite(self.score):
            raise ValueError("Vector search candidate must have a valid ID and score.")


@dataclass(frozen=True)
class ActiveChunk:
    """Repository 从 MySQL 读取的、属于当前 active Version 的可检索 Chunk。"""

    chunk_id: str
    document_id: str
    file_id: str
    content: str
    source_locator: SourceLocator


@dataclass(frozen=True)
class RetrievalHit:
    """
    已经通过 MySQL 范围和 active Version 校验的检索结果。

    后续 ContextBuilder 使用 content 与 score 选择上下文，Citation 使用 document_id、file_id
    和 source_locator 生成可追溯来源；本对象不包含 Qdrant SDK 类型或向量数据。
    """

    chunk_id: str
    document_id: str
    file_id: str
    content: str
    source_locator: SourceLocator
    score: float
