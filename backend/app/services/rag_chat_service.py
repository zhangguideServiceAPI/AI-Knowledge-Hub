"""RAG Chat 的 Service 编排入口。"""

from app.knowledge.retrieval import RetrievalHit
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
    ) -> None:
        """注入知识检索 Service 和服务器侧检索配置，不从用户请求读取检索策略。"""

        self._knowledge_service = knowledge_service
        self._retrieval_components = retrieval_components

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
