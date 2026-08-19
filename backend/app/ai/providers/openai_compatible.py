from collections.abc import AsyncIterator

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)

from app.ai.exceptions import (
    ProviderError,
    ProviderRateLimitError,
    ProviderStreamError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.ai.provider import (
    ChatDelta,
    ChatDone,
    ChatEvent,
    ChatResult,
    ChatUsageEvent,
    ProviderEmbeddingRequest,
    ProviderEmbeddingResult,
    FinishReason,
    ProviderChatRequest,
    TokenUsage,
)


_FINISH_REASON_MAP = {
    "stop": FinishReason.STOP,
    "length": FinishReason.LENGTH,
    "content_filter": FinishReason.CONTENT_FILTER,
}


def _translate_sdk_error(error: APIError) -> ProviderError:
    if isinstance(error, RateLimitError):
        return ProviderRateLimitError("Provider rate limit exceeded.")
    if isinstance(error, APITimeoutError):
        return ProviderTimeoutError("Provider request timed out.")
    if isinstance(error, (APIConnectionError, InternalServerError)):
        return ProviderUnavailableError("Provider is temporarily unavailable.")
    return ProviderError("Provider request failed.")


def _token_usage(usage: object) -> TokenUsage:
    return TokenUsage(
        input_tokens=getattr(usage, "prompt_tokens", None),
        output_tokens=getattr(usage, "completion_tokens", None),
        total_tokens=getattr(usage, "total_tokens", None),
    )


class OpenAICompatibleChatProvider:
    def __init__(self, client: AsyncOpenAI) -> None:
        self.client = client

    async def generate(self, request: ProviderChatRequest) -> ChatResult:
        try:
            response = await self.client.chat.completions.create(
                model=request.provider_model,
                messages=[
                    {
                        "role": message.role.value,
                        "content": message.content,
                    }
                    for message in request.messages
                ],
                temperature=request.temperature,
                max_tokens=request.max_output_tokens,
                stream=False,
            )
        except APIError as exc:
            raise _translate_sdk_error(exc) from exc

        choices = getattr(response, "choices", None)
        if not isinstance(choices, (list, tuple)):
            raise ProviderError("Provider returned a malformed response.")
        if not choices:
            raise ProviderError("Provider returned no choices.")

        choice = choices[0]
        finish_reason = _FINISH_REASON_MAP.get(getattr(choice, "finish_reason", None))

        if finish_reason is None:
            raise ProviderError("Provider returned an unsupported finish reason.")

        usage = None
        response_usage = getattr(response, "usage", None)
        if response_usage is not None:
            usage = _token_usage(response_usage)

        message = getattr(choice, "message", None)
        content = getattr(message, "content", None)
        if content is not None and not isinstance(content, str):
            raise ProviderError("Provider returned malformed message content.")

        return ChatResult(
            request_id=request.request_id,
            content=content or "",
            finish_reason=finish_reason,
            usage=usage,
        )

    async def stream(self, request: ProviderChatRequest) -> AsyncIterator[ChatEvent]:
        sdk_stream = None
        finish_reason = None
        usage = None
        emitted_event = False
        # 按 delta -> usage -> done 顺序输出
        try:
            sdk_stream = await self.client.chat.completions.create(
                model=request.provider_model,
                messages=[
                    {
                        "role": message.role.value,
                        "content": message.content,
                    }
                    for message in request.messages
                ],
                temperature=request.temperature,
                max_tokens=request.max_output_tokens,
                stream=True,
                stream_options={"include_usage": True},
            )

            async for chunk in sdk_stream:
                chunk_usage = getattr(chunk, "usage", None)
                if chunk_usage is not None:
                    usage = _token_usage(chunk_usage)

                choices = getattr(chunk, "choices", None)
                if not isinstance(choices, (list, tuple)):
                    raise ProviderStreamError(
                        "Provider returned a malformed stream event."
                    )
                if not choices:
                    continue

                choice = choices[0]
                raw_finish_reason = getattr(choice, "finish_reason", None)
                if raw_finish_reason is not None:
                    finish_reason = _FINISH_REASON_MAP.get(raw_finish_reason)
                    if finish_reason is None:
                        raise ProviderStreamError(
                            "Provider returned an unsupported finish reason."
                        )

                content = getattr(getattr(choice, "delta", None), "content", None)
                if content:
                    emitted_event = True
                    yield ChatDelta(
                        request_id=request.request_id,
                        content=content,
                    )

            if finish_reason is None:
                raise ProviderStreamError(
                    "Provider stream ended without a finish reason."
                )

            if usage is not None:
                emitted_event = True
                yield ChatUsageEvent(
                    request_id=request.request_id,
                    usage=usage,
                )

            emitted_event = True
            yield ChatDone(
                request_id=request.request_id,
                finish_reason=finish_reason,
            )
        except APIError as exc:
            if emitted_event:
                raise ProviderStreamError("Provider stream was interrupted.") from exc
            raise _translate_sdk_error(exc) from exc
        finally:
            if sdk_stream is not None:
                await sdk_stream.close()


class OpenAICompatibleEmbeddingProvider:
    """使用 OpenAI-compatible `/embeddings` API 处理一批文本。"""

    def __init__(self, client: AsyncOpenAI) -> None:
        """保存已配置认证、Base URL 与超时的异步 OpenAI 客户端。"""

        self._client = client

    async def embed(
        self,
        request: ProviderEmbeddingRequest,
    ) -> ProviderEmbeddingResult:
        """请求 Provider Embedding API，并按响应 index 恢复与输入相同的文本顺序。"""

        try:
            response = await self._client.embeddings.create(
                model=request.provider_model,
                input=list(request.texts),
            )
        except APIError as error:
            raise _translate_sdk_error(error) from error

        response_data = getattr(response, "data", None)
        if not isinstance(response_data, (list, tuple)):
            raise ProviderError("Provider returned a malformed embedding response.")
        if len(response_data) != len(request.texts):
            raise ProviderError("Provider returned an unexpected embedding count.")

        indexed_vectors: list[tuple[int, tuple[float, ...]]] = []
        for item in response_data:
            index = getattr(item, "index", None)
            vector = getattr(item, "embedding", None)
            if not isinstance(index, int) or not isinstance(vector, (list, tuple)):
                raise ProviderError("Provider returned a malformed embedding item.")
            if not all(isinstance(value, (float, int)) for value in vector):
                raise ProviderError("Provider returned a non-numeric embedding value.")
            indexed_vectors.append((index, tuple(float(value) for value in vector)))

        indexed_vectors.sort(key=lambda item: item[0])
        if [index for index, _vector in indexed_vectors] != list(
            range(len(request.texts))
        ):
            raise ProviderError("Provider returned invalid embedding indexes.")

        return ProviderEmbeddingResult(
            request_id=request.request_id,
            vectors=tuple(vector for _index, vector in indexed_vectors),
        )
