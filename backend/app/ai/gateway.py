from collections.abc import Callable, Mapping
from dataclasses import dataclass
import asyncio

from app.ai.exceptions import (
    AIInvalidModelError,
    AIInvalidRequestError,
    AIProviderError,
    AIProviderRateLimitError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.ai.provider import (
    ChatMessage,
    ChatProvider,
    ChatResult,
    FinishReason,
    ProviderChatRequest,
    TokenUsage,
)
from app.core.config import AIModelConfig


_INPUT_MESSAGE_TOKEN_OVERHEAD = 4
_INPUT_REPLY_PRIMER_TOKENS = 2


def _estimate_input_tokens_conservatively(
    _provider_model: str,
    messages: tuple[ChatMessage, ...],
) -> int:
    return _INPUT_REPLY_PRIMER_TOKENS + sum(
        _INPUT_MESSAGE_TOKEN_OVERHEAD
        + len(message.role.value.encode("utf-8"))
        + len(message.content.encode("utf-8"))
        for message in messages
    )


def _translate_provider_error(error: ProviderError) -> AIProviderError:
    if isinstance(error, ProviderRateLimitError):
        return AIProviderRateLimitError("AI provider rate limit exceeded.")

    if isinstance(error, ProviderTimeoutError):
        return AIProviderTimeoutError("AI provider request timed out.")

    if isinstance(error, ProviderUnavailableError):
        return AIProviderUnavailableError("AI provider is unavailable.")

    return AIProviderUnavailableError("AI provider request failed.")


def _is_retryable_provider_error(error: ProviderError) -> bool:
    return isinstance(
        error,
        (
            ProviderRateLimitError,
            ProviderTimeoutError,
            ProviderUnavailableError,
        ),
    )


@dataclass(frozen=True)
class ChatRequest:
    request_id: str
    messages: tuple[ChatMessage, ...]
    model_alias: str | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None


@dataclass(frozen=True)
class GatewayChatResult:
    request_id: str
    model_alias: str
    content: str
    finish_reason: FinishReason
    usage: TokenUsage | None


class AIGateway:
    def __init__(
        self,
        *,
        model_configs: Mapping[str, AIModelConfig],
        default_model_alias: str | None,
        provider_factory: Callable[[str], ChatProvider],
        max_retry_attempts: int,
        retry_backoff_seconds: float,
        total_deadline_seconds: float,
        input_token_estimator: Callable[
            [str, tuple[ChatMessage, ...]],
            int,
        ] = _estimate_input_tokens_conservatively,
    ) -> None:
        self._model_configs = model_configs
        self._default_model_alias = default_model_alias
        self._provider_factory = provider_factory
        self._max_retry_attempts = max_retry_attempts
        self._retry_backoff_seconds = retry_backoff_seconds
        self._total_deadline_seconds = total_deadline_seconds
        self._input_token_estimator = input_token_estimator

    async def generate(
        self,
        request: ChatRequest,
    ) -> GatewayChatResult:
        model_alias = request.model_alias
        if model_alias is None:
            model_alias = self._default_model_alias

        if model_alias is None:
            raise AIInvalidModelError("No default AI model is configured.")

        model_config = self._model_configs.get(model_alias)
        if model_config is None:
            raise AIInvalidModelError("Requested AI model is not configured.")

        temperature = request.temperature
        if temperature is None:
            temperature = model_config.default_temperature

        max_output_tokens = request.max_output_tokens
        if max_output_tokens is None:
            max_output_tokens = model_config.default_max_output_tokens

        if not 0.0 <= temperature <= 2.0:
            raise AIInvalidRequestError("temperature must be between 0.0 and 2.0.")

        if max_output_tokens <= 0 or max_output_tokens > model_config.max_output_tokens:
            raise AIInvalidRequestError("max_output_tokens exceeds the allowed range.")

        estimated_input_tokens = self._input_token_estimator(
            model_config.provider_model,
            request.messages,
        )

        if (
            estimated_input_tokens + max_output_tokens
            > model_config.context_window_tokens
        ):
            raise AIInvalidRequestError(
                "input token estimate plus max_output_tokens "
                "exceeds the model context window."
            )

        provider = self._provider_factory(model_config.provider_key)

        provider_request = ProviderChatRequest(
            request_id=request.request_id,
            messages=request.messages,
            provider_model=model_config.provider_model,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )

        try:
            # 这是整个“首次调用 + 等待 + 重试”的总时间上限。
            async with asyncio.timeout(
                self._total_deadline_seconds
            ):  # 它会为一段异步代码设置截止时间。超时后内部任务会被取消，离开上下文后转换为 TimeoutError。
                provider_result = await self._generate_with_retry(
                    provider,
                    provider_request,
                )
        except TimeoutError as error:
            raise AIProviderTimeoutError("AI provider request timed out.") from error
        except ProviderError as error:
            raise _translate_provider_error(error) from error

        return GatewayChatResult(
            request_id=provider_result.request_id,
            model_alias=model_alias,
            content=provider_result.content,
            finish_reason=provider_result.finish_reason,
            usage=provider_result.usage,
        )

    async def _generate_with_retry(
        self,
        provider: ChatProvider,
        request: ProviderChatRequest,
    ) -> ChatResult:
        retry_count = 0

        while True:
            try:
                return await provider.generate(request)
            except ProviderError as error:
                if (
                    not _is_retryable_provider_error(error)
                    or retry_count >= self._max_retry_attempts
                ):
                    raise
                # 指数退避更适合 Rate Limit 或 Provider 暂时故障。大量请求同时失败时，如果大家都固定等待 0.2 秒，就会在同一时间再次冲击 Provider。指数退避会逐渐拉开请求时间。
                # **：幂运算，2**3 等于 8
                backoff_seconds = self._retry_backoff_seconds * (2**retry_count)

                if backoff_seconds > 0:
                    await asyncio.sleep(backoff_seconds)

                retry_count += 1
