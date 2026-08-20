"""RAG 请求的模型 Context Window 与知识 Context 预算计算。"""

from dataclasses import dataclass

from app.core.config import AIModelConfig
from app.knowledge.chunking import TokenCounter


class RAGTokenBudgetError(ValueError):
    """RAG 请求无法在模型 Context Window 内保留必要输入和输出空间。"""


@dataclass(frozen=True)
class RAGTokenBudget:
    """一次 RAG 请求最终可交给 ContextBuilder 使用的 Token 预算快照。"""

    context_window_tokens: int
    max_output_tokens: int
    reserved_input_tokens: int
    safety_margin_tokens: int
    available_context_tokens: int

    def __post_init__(self) -> None:
        """校验预算各组成部分非负，并确保可用 Context 不会突破总窗口。"""

        values = (
            self.context_window_tokens,
            self.max_output_tokens,
            self.reserved_input_tokens,
            self.safety_margin_tokens,
            self.available_context_tokens,
        )
        if any(value < 0 for value in values):
            raise RAGTokenBudgetError("RAG token budget values must not be negative.")
        if (
            self.max_output_tokens
            + self.reserved_input_tokens
            + self.safety_margin_tokens
            + self.available_context_tokens
            > self.context_window_tokens
        ):
            raise RAGTokenBudgetError(
                "RAG token budget exceeds the model context window."
            )


class RAGTokenBudgetCalculator:
    """使用 Chat 模型配置和实际 TokenCounter 计算知识 Context 可用空间。"""

    def __init__(
        self,
        *,
        token_counter: TokenCounter,
        safety_margin_tokens: int,
    ) -> None:
        """注入 Chat 模型 tokenizer 和服务器安全余量，不接受客户端自行扩大余量。"""

        if safety_margin_tokens < 0:
            raise RAGTokenBudgetError("RAG safety margin must not be negative.")
        self._token_counter = token_counter
        self._safety_margin_tokens = safety_margin_tokens

    def calculate(
        self,
        *,
        model_config: AIModelConfig,
        system_prompt: str,
        user_messages: tuple[str, ...],
        max_output_tokens: int | None = None,
    ) -> RAGTokenBudget:
        """
        计算 System/User 输入之后可放入 RAG Context 的 Token 数。

        输入文本按 Chat 模型 tokenizer 计数；输出上限使用请求值或服务器默认值，并且不能
        超过模型允许的最大值。System Prompt、用户消息、输出预留和安全余量都先扣除；若
        没有任何知识 Context 空间则抛出错误，避免发送必然超过 Context Window 的请求。
        本方法不访问 PromptCenter、数据库、Qdrant 或 AI Provider。
        """

        if not system_prompt.strip():
            raise RAGTokenBudgetError("RAG system prompt must not be empty.")
        if not user_messages or any(not message.strip() for message in user_messages):
            raise RAGTokenBudgetError("RAG user messages must not be empty.")

        resolved_output_tokens = (
            model_config.default_max_output_tokens
            if max_output_tokens is None
            else max_output_tokens
        )
        if resolved_output_tokens <= 0:
            raise RAGTokenBudgetError(
                "RAG output token limit must be greater than zero."
            )
        if resolved_output_tokens > model_config.max_output_tokens:
            raise RAGTokenBudgetError(
                "RAG output token limit exceeds the model maximum."
            )

        reserved_input_tokens = self._token_counter.count(system_prompt) + sum(
            self._token_counter.count(message) for message in user_messages
        )
        available_context_tokens = (
            model_config.context_window_tokens
            - reserved_input_tokens
            - resolved_output_tokens
            - self._safety_margin_tokens
        )
        if available_context_tokens < 0:
            raise RAGTokenBudgetError(
                "RAG prompt and output reservation exceed the model context window."
            )

        return RAGTokenBudget(
            context_window_tokens=model_config.context_window_tokens,
            max_output_tokens=resolved_output_tokens,
            reserved_input_tokens=reserved_input_tokens,
            safety_margin_tokens=self._safety_margin_tokens,
            available_context_tokens=available_context_tokens,
        )
