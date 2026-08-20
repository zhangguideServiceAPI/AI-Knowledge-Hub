"""RAG Chat 编排阶段的输入输出契约。"""

from dataclasses import dataclass
from typing import Protocol

from app.ai.provider import FinishReason, TokenUsage
from app.knowledge.context import Citation


class RAGContractError(ValueError):
    """RAG 结果不符合对内服务契约。"""


@dataclass(frozen=True)
class RAGAnswer:
    """RAG ChatService 返回给 API 层的回答、模型终态、Usage 和来源。"""

    request_id: str
    model: str
    content: str
    finish_reason: FinishReason
    citations: tuple[Citation, ...]
    usage: TokenUsage | None = None

    def __post_init__(self) -> None:
        """校验回答身份和 Citation 集合，防止空请求标识进入响应或日志链路。"""

        if not self.request_id.strip():
            raise RAGContractError("RAG request ID must not be empty.")
        if not self.model.strip():
            raise RAGContractError("RAG model must not be empty.")
        citation_ids = tuple(citation.citation_id for citation in self.citations)
        if len(citation_ids) != len(set(citation_ids)):
            raise RAGContractError("RAG citation IDs must be unique.")


class RAGChatService(Protocol):
    """RAG 问答编排边界，负责把检索、Context、Prompt 和 ChatService 串成一次请求。"""

    async def answer_knowledge_question(
        self,
        *,
        owner_id: int,
        knowledge_base_id: str,
        query: str,
        model_alias: str | None = None,
        max_output_tokens: int | None = None,
    ) -> RAGAnswer:
        """
        根据用户问题生成带 Citation 的知识库回答。

        `owner_id` 来自认证用户，`knowledge_base_id` 和 `query` 来自业务请求；模型别名与
        输出上限只能在服务器配置允许的范围内生效。实现必须先完成 Retrieval 和 Context
        预算，再通过 PromptCenter 与现有 ChatService/AIGateway 生成回答；本协议不允许
        Router 直接访问 Qdrant、Prompt 模板或 Provider SDK。
        """

        ...
