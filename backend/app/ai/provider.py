from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class ChatRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class FinishReason(StrEnum):
    STOP = "stop"
    LENGTH = "length"
    CONTENT_FILTER = "content_filter"


@dataclass(frozen=True)
class ChatMessage:
    role: ChatRole
    content: str


@dataclass(frozen=True)
class ProviderChatRequest:
    request_id: str
    messages: tuple[ChatMessage, ...]
    provider_model: str
    temperature: float
    max_output_tokens: int


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


@dataclass(frozen=True)
class ChatResult:
    request_id: str
    content: str
    finish_reason: FinishReason
    usage: TokenUsage | None


@dataclass(frozen=True)
class ProviderEmbeddingRequest:
    """发送给具体 Embedding Provider 的一批文本及 Provider 模型名。"""

    request_id: str
    texts: tuple[str, ...]
    provider_model: str


@dataclass(frozen=True)
class ProviderEmbeddingResult:
    """Provider 返回的、与请求文本保持相同顺序的一批数值向量。"""

    request_id: str
    vectors: tuple[tuple[float, ...], ...]


@dataclass(frozen=True)
class ChatDelta:
    request_id: str
    content: str


@dataclass(frozen=True)
class ChatUsageEvent:
    request_id: str
    usage: TokenUsage


@dataclass(frozen=True)
class ChatDone:
    request_id: str
    finish_reason: FinishReason


type ChatEvent = ChatDelta | ChatUsageEvent | ChatDone


class ChatProvider(Protocol):
    async def generate(self, request: ProviderChatRequest) -> ChatResult: ...

    def stream(self, request: ProviderChatRequest) -> AsyncIterator[ChatEvent]: ...


class EmbeddingProvider(Protocol):
    """把一批文本转换为数值向量的 Provider 能力边界。"""

    async def embed(
        self,
        request: ProviderEmbeddingRequest,
    ) -> ProviderEmbeddingResult:
        """调用 Provider 的 Embedding API，并返回与输入文本顺序一致的向量。"""

        ...
