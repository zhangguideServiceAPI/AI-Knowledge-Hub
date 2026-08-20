"""RAG Chat 的 Service 编排入口。"""

from collections.abc import Mapping

from app.core.config import AIModelConfig
from app.knowledge.retrieval import RetrievalHit
from app.knowledge.budget import RAGTokenBudgetCalculator
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
        budget_calculator: RAGTokenBudgetCalculator,
        model_configs: Mapping[str, AIModelConfig],
        default_model_alias: str | None,
    ) -> None:
        """注入检索、Context、预算和 Chat 模型配置，不从用户请求读取服务器策略。"""

        self._knowledge_service = knowledge_service
        self._retrieval_components = retrieval_components
        self._context_builder = context_builder
        self._budget_calculator = budget_calculator
        self._model_configs = model_configs
        self._default_model_alias = default_model_alias

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
        system_prompt: str,
        model_alias: str | None = None,
        max_output_tokens: int | None = None,
    ) -> BuiltContext:
        """
        先计算真实预算，再检索当前有效 Chunk 并构造 Context 和 Citation。

        `system_prompt` 由下一步 PromptCenter 提供；模型配置、Tokenizer 和安全余量来自
        服务端注入。方法自动扣除 System/User 输入、输出预留与安全余量，剩余空间才交给
        ContextBuilder。本方法仍不渲染 Prompt、不调用 ChatService 或 AIGateway；没有命中
        时返回空 BuiltContext，保留“无依据时不生成回答”的判断权给上层。
        """

        model_config = self._resolve_model_config(model_alias)
        budget = self._budget_calculator.calculate(
            model_config=model_config,
            system_prompt=system_prompt,
            user_messages=(query,),
            max_output_tokens=max_output_tokens,
        )
        hits = await self.retrieve_hits(
            owner_id=owner_id,
            knowledge_base_id=knowledge_base_id,
            query=query,
        )
        return self._context_builder.build(
            hits=hits,
            token_budget=budget.available_context_tokens,
        )

    def _resolve_model_config(self, model_alias: str | None) -> AIModelConfig:
        """解析请求模型别名；未指定时使用服务器默认值，未知别名拒绝进入预算计算。"""

        resolved_alias = model_alias or self._default_model_alias
        if resolved_alias is None:
            raise ValueError("No default RAG chat model is configured.")
        model_config = self._model_configs.get(resolved_alias)
        if model_config is None:
            raise ValueError("Requested RAG chat model is not configured.")
        return model_config
