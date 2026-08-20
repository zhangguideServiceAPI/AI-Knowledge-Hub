"""将已校验的检索命中组织为受 Token 预算限制的 RAG Context。"""

from dataclasses import dataclass

from app.knowledge.chunking import TokenCounter
from app.knowledge.parsing import SourceLocator
from app.knowledge.retrieval import RetrievalHit


class ContextBuildError(ValueError):
    """Context 的 Token 预算或中间数据不符合构建契约。"""


@dataclass(frozen=True)
class Citation:
    """一个实际进入 Context 的 Chunk 的结构化可追溯来源。"""

    citation_id: str
    chunk_id: str
    document_id: str
    file_id: str
    source_locator: SourceLocator

    def __post_init__(self) -> None:
        """创建 Citation 后校验稳定引用标识和来源元数据，拒绝无效的对外追溯记录。"""

        if not all(
            value.strip()
            for value in (
                self.citation_id,
                self.chunk_id,
                self.document_id,
                self.file_id,
            )
        ):
            raise ContextBuildError("Citation identifiers must not be empty.")
        if not self.source_locator:
            raise ContextBuildError("Citation source locator must not be empty.")


@dataclass(frozen=True)
class BuiltContext:
    """ContextBuilder 的内存结果，供后续 RAG Prompt 组装和 API Citation 响应复用。"""

    content: str
    citations: tuple[Citation, ...]
    used_tokens: int

    def __post_init__(self) -> None:
        """校验 Token 用量非负，且空 Context 不会携带无法对应正文的 Citation。"""

        if self.used_tokens < 0:
            raise ContextBuildError("Context used tokens must not be negative.")
        if not self.content and self.citations:
            raise ContextBuildError("Empty context must not contain citations.")


class ContextBuilder:
    """按 RetrievalHit 的既有相关度顺序选择完整 Chunk，绝不为塞入预算截断原文。"""

    def __init__(self, *, token_counter: TokenCounter) -> None:
        """注入与目标 Chat 模型匹配的 TokenCounter；本组件不自行猜测字符数或字节数。"""

        self._token_counter = token_counter

    def build(
        self,
        *,
        hits: tuple[RetrievalHit, ...],
        token_budget: int,
    ) -> BuiltContext:
        """
        在预算内将已校验命中拼为带来源标签的 Context，并返回采用的 Citation。

        输入必须是 5.7 已经过 MySQL active Version 校验、且已按检索分数排序的命中；
        `token_budget` 由上层在扣除 System Prompt、用户问题和输出预留后提供。每次尝试
        都对最终拼接文本重新计数，以覆盖标签和分隔符的 Token；超预算 Chunk 整块跳过，
        继续尝试后续较小 Chunk。本方法不访问数据库、Qdrant 或 AI Provider。
        """

        if token_budget < 0:
            raise ContextBuildError("Context token budget must not be negative.")

        fragments: list[str] = []
        citations: list[Citation] = []
        used_tokens = 0

        for hit in hits:
            citation_id = f"source-{len(citations) + 1}"
            citation = Citation(
                citation_id=citation_id,
                chunk_id=hit.chunk_id,
                document_id=hit.document_id,
                file_id=hit.file_id,
                source_locator=hit.source_locator,
            )
            fragment = self._format_fragment(
                citation_id=citation_id, content=hit.content
            )
            candidate_content = "\n\n".join((*fragments, fragment))
            candidate_tokens = self._token_counter.count(candidate_content)

            if candidate_tokens > token_budget:
                # 不截断原文，保证 Citation 永远能指向完整、可读的 Chunk。
                continue

            fragments.append(fragment)
            citations.append(citation)
            used_tokens = candidate_tokens

        return BuiltContext(
            content="\n\n".join(fragments),
            citations=tuple(citations),
            used_tokens=used_tokens,
        )

    def _format_fragment(self, *, citation_id: str, content: str) -> str:
        """将一个 Chunk 包装为明确边界的受控 Context 片段，供 build 计数并拼接。"""

        normalized_content = content.strip()
        if not normalized_content:
            raise ContextBuildError("Retrieval hit content must not be empty.")
        return (
            f'<knowledge_context source_id="{citation_id}">\n'
            f"{normalized_content}\n"
            "</knowledge_context>"
        )
