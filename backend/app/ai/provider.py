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
