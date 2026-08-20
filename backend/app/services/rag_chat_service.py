"""RAG Chat 的 Service 编排入口。"""

from app.knowledge.retrieval import RetrievalHit
from app.knowledge.context import BuiltContext, ContextBuilder
from app.services.knowledge_service import (
    KnowledgeRetrievalComponents,
    KnowledgeService,
)


class RAGChatService:
    """按固定顺序连接 Knowledge Retrieval、Context、Prompt 和 Chat 能力。"""

    def __init__(
        self,
        knowledge_service: KnowledgeService,
        retrieval_components: KnowledgeRetrievalComponents,
        context_builder: ContextBuilder,
    ) -> None:
        """注入检索、Context 能力和服务器策略，不从用户请求读取内部实现配置。"""

        self._knowledge_service = knowledge_service
        self._retrieval_components = retrieval_components
        self._context_builder = context_builder

    async def retrieve_hits(
        self,
        *,
        owner_id: int,
        knowledge_base_id: str,
        query: str,
    ) -> tuple[RetrievalHit, ...]:
        """
        为一次 RAG 问答取得已经过权限和 active Version 校验的检索命中。

        输入来自认证用户、目标 KnowledgeBase 和用户问题；检索策略、Embedding 模型与
        Qdrant 连接来自服务器注入的组件。输出仍是 RetrievalHit，不构造 Prompt、不调用
        ChatService，也不改变任何索引状态。没有命中时返回空 tuple，由上层决定是否生成回答。
        """

        return await self._knowledge_service.search_knowledge(
            owner_id=owner_id,
            knowledge_base_id=knowledge_base_id,
            query=query,
            components=self._retrieval_components,
        )

    async def retrieve_context(
        self,
        *,
        owner_id: int,
        knowledge_base_id: str,
        query: str,
        token_budget: int,
    ) -> BuiltContext:
        """
        先检索当前有效 Chunk，再在给定 Token 预算内构造 Context 和 Citation。

        `token_budget` 来自上层对 Chat 模型 Context Window 的预算计算，不由用户直接放大；
        本方法只串联 Retrieval 与 ContextBuilder，不渲染 Prompt、不调用 ChatService 或
        AIGateway。没有命中时返回空 BuiltContext，保留“无依据时不生成回答”的判断权给上层。
        """

        hits = await self.retrieve_hits(
            owner_id=owner_id,
            knowledge_base_id=knowledge_base_id,
            query=query,
        )
        return self._context_builder.build(
            hits=hits,
            token_budget=token_budget,
        )
