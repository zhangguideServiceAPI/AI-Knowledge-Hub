"""RAG Chat 的 Service 编排入口。"""

from collections.abc import Mapping

from app.ai.prompt_center import PromptCenter
from app.ai.provider import TokenUsage
from app.ai.exceptions import AIInvalidModelError
from app.core.config import AIModelConfig
from app.knowledge.budget import RAGTokenBudgetCalculator
from app.knowledge.context import BuiltContext, ContextBuilder
from app.knowledge.rag import PreparedRAGPrompt, RAGAnswer
from app.knowledge.retrieval import RetrievalHit
from app.schemas.ai import ChatMessageInput, ChatRequestSchema
from app.services.chat_service import ChatService
from app.services.knowledge_service import (
    KnowledgeRetrievalComponents,
    KnowledgeService,
)

_RAG_PROMPT_KEY = "rag_assistant"
_RAG_PROMPT_VERSION = "v1"


class RAGChatService:
    """按固定顺序连接 Knowledge Retrieval、Context、Prompt 和 Chat 能力。"""

    def __init__(
        self,
        knowledge_service: KnowledgeService,
        retrieval_components: KnowledgeRetrievalComponents,
        context_builder: ContextBuilder,
        budget_calculator: RAGTokenBudgetCalculator,
        prompt_center: PromptCenter,
        chat_service: ChatService,
        model_configs: Mapping[str, AIModelConfig],
        default_model_alias: str | None,
    ) -> None:
        """注入检索、Context、预算和 Chat 模型配置，不从用户请求读取服务器策略。"""

        self._knowledge_service = knowledge_service
        self._retrieval_components = retrieval_components
        self._context_builder = context_builder
        self._budget_calculator = budget_calculator
        self._prompt_center = prompt_center
        self._chat_service = chat_service
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

    async def prepare_prompt_context(
        self,
        *,
        owner_id: int,
        knowledge_base_id: str,
        query: str,
        model_alias: str | None = None,
        max_output_tokens: int | None = None,
    ) -> PreparedRAGPrompt:
        """
        以空 Context 渲染基础 Prompt 计算预算，再注入检索结果得到最终 System Prompt。

        第一次渲染保留模板的固定指令、标签和换行，确保它们也占用 Token 预算；随后使用
        BuiltContext 的正文再次渲染相同版本模板。输出保留 Prompt 身份、最终正文和 Citation，
        供下一步 ChatService/AIGateway 调用复用。本方法不直接调用模型。
        """

        base_prompt = self._prompt_center.render(
            prompt_key=_RAG_PROMPT_KEY,
            version=_RAG_PROMPT_VERSION,
            variables={"knowledge_context": ""},
        )
        context = await self.retrieve_context(
            owner_id=owner_id,
            knowledge_base_id=knowledge_base_id,
            query=query,
            system_prompt=base_prompt.content,
            model_alias=model_alias,
            max_output_tokens=max_output_tokens,
        )
        rendered_prompt = self._prompt_center.render(
            prompt_key=_RAG_PROMPT_KEY,
            version=_RAG_PROMPT_VERSION,
            variables={"knowledge_context": context.content},
        )
        return PreparedRAGPrompt(
            rendered_prompt=rendered_prompt,
            context_content=context.content,
            citations=context.citations,
            context_tokens=context.used_tokens,
        )

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
        生成一次携带结构化 Citation 的非流式 RAG 回答。

        本方法先准备受预算约束的 RAG Prompt，再把用户问题作为唯一 USER Message 交给
        ChatService；后者统一负责 AIGateway、Usage、成本、超时、重试和错误转换。模型
        不直接接收数据库 ID，Citation 由 PreparedRAGPrompt 单独保留并随回答返回。
        """

        prepared_prompt = await self.prepare_prompt_context(
            owner_id=owner_id,
            knowledge_base_id=knowledge_base_id,
            query=query,
            model_alias=model_alias,
            max_output_tokens=max_output_tokens,
        )
        response = await self._chat_service.chat_with_rendered_prompt(
            ChatRequestSchema(
                messages=[ChatMessageInput(content=query)],
                model=model_alias,
                max_output_tokens=max_output_tokens,
            ),
            user_id=owner_id,
            rendered_prompt=prepared_prompt.rendered_prompt,
        )
        usage = None
        if response.usage is not None:
            usage = TokenUsage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                total_tokens=response.usage.total_tokens,
            )
        return RAGAnswer(
            request_id=response.request_id,
            model=response.model,
            content=response.content,
            finish_reason=response.finish_reason,
            citations=prepared_prompt.citations,
            usage=usage,
        )

    def _resolve_model_config(self, model_alias: str | None) -> AIModelConfig:
        """第一版 RAG 固定默认 Chat 模型，避免不同模型复用错误 tokenizer。"""

        resolved_alias = model_alias or self._default_model_alias
        if resolved_alias is None:
            raise AIInvalidModelError("No default RAG chat model is configured.")
        if resolved_alias != self._default_model_alias:
            raise AIInvalidModelError(
                "RAG currently supports only the default chat model."
            )
        model_config = self._model_configs.get(resolved_alias)
        if model_config is None:
            raise AIInvalidModelError("Requested RAG chat model is not configured.")
        return model_config
