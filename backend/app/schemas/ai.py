from enum import StrEnum
from typing import Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeInt,
    field_validator,
    model_validator,
)

from app.ai.provider import FinishReason
from app.schemas.error import ErrorResponse

MAX_CHAT_MESSAGES = 20
MAX_CHAT_MESSAGE_CONTENT_LENGTH = 8_000
MAX_CHAT_TOTAL_CONTENT_LENGTH = 32_000

MODEL_ALIAS_PATTERN = r"^[A-Za-z0-9._-]+$"


# StrEnum 的成员既是枚举值也是字符串，可避免代码中到处手写错误码。
class AIErrorCode(StrEnum):
    INVALID_MODEL = "ai_invalid_model"
    INVALID_REQUEST = "ai_invalid_request"
    PROVIDER_RATE_LIMIT = "ai_provider_rate_limit"
    PROVIDER_TIMEOUT = "ai_provider_timeout"
    PROVIDER_UNAVAILABLE = "ai_provider_unavailable"
    INTERNAL_ERROR = "ai_internal_error"


class AIErrorResponse(ErrorResponse):
    model_config = ConfigDict(extra="forbid")

    code: AIErrorCode


# ConfigDict(extra="ignore")  # 忽略，通常也是默认行为
# ConfigDict(extra="allow")   # 接受并保留
# ConfigDict(extra="forbid")  # 直接拒绝
class ChatMessageInput(BaseModel):
    # 拒绝 role、provider 等未声明字段。  模型只声明了 content 所以传入参数就只能是 content 如果有其他的参数都拒绝报错
    model_config = ConfigDict(extra="forbid")

    content: str = Field(
        min_length=1,
        max_length=MAX_CHAT_MESSAGE_CONTENT_LENGTH,
    )

    @field_validator("content")
    @classmethod
    def validate_content_not_blank(cls, content: str) -> str:
        if not content.strip():
            raise ValueError("message content must not be blank.")

        return content


class ChatRequestSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[ChatMessageInput] = Field(
        min_length=1,
        max_length=MAX_CHAT_MESSAGES,
    )
    model: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=MODEL_ALIAS_PATTERN,
    )
    temperature: float | None = Field(
        default=None,
        ge=0.0,
        le=2.0,
    )
    max_output_tokens: int | None = Field(
        default=None,
        gt=0,
    )

    @model_validator(mode="after")
    def validate_total_content_length(self) -> Self:
        total_length = sum(len(message.content) for message in self.messages)
        if total_length > MAX_CHAT_TOTAL_CONTENT_LENGTH:
            raise ValueError("total message content is too long.")

        return self


class ChatUsageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # None 表示 Provider 没有返回可信统计，不能伪造为零。
    # NonNegativeInt 它是 Pydantic 提供的受约束整数： >= 0
    input_tokens: NonNegativeInt | None
    output_tokens: NonNegativeInt | None
    total_tokens: NonNegativeInt | None


class ChatResponseSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(
        min_length=1,
        max_length=128,
    )
    model: str = Field(
        min_length=1,
        max_length=64,
        pattern=MODEL_ALIAS_PATTERN,
    )
    # content_filter 等合法终态可能没有可展示正文，因此不限制最小长度。
    content: str
    finish_reason: FinishReason
    usage: ChatUsageResponse | None = None
