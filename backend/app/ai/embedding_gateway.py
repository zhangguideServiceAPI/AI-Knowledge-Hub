"""Embedding 模型的批量调用边界与返回契约校验。"""

import asyncio
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from app.ai.exceptions import (
    AIProviderError,
    AIInvalidModelError,
    AIInvalidRequestError,
    AIProviderRateLimitError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.ai.provider import (
    EmbeddingProvider,
    ProviderEmbeddingRequest,
)
from app.core.config import EmbeddingModelConfig


@dataclass(frozen=True)
class EmbeddingRequest:
    """KnowledgeService 发送给 EmbeddingGateway 的一批 Chunk 文本。"""

    request_id: str
    texts: tuple[str, ...]
    model_alias: str | None = None


@dataclass(frozen=True)
class GatewayEmbeddingResult:
    """Gateway 已验证数量、顺序和维度后返回给业务层的向量结果。"""

    request_id: str
    model_alias: str
    vectors: tuple[tuple[float, ...], ...]


@dataclass(frozen=True)
class _PreparedEmbeddingCall:
    """Gateway 解析模型别名后交给具体 Provider 的调用信息。"""

    model_alias: str
    dimension: int
    provider: EmbeddingProvider
    provider_request: ProviderEmbeddingRequest


class EmbeddingGateway:
    """将 Embedding Provider 差异隔离在统一批量调用与验证边界之后。"""

    def __init__(
        self,
        *,
        model_configs: Mapping[str, EmbeddingModelConfig],
        default_model_alias: str | None,
        provider_factory: Callable[[str], EmbeddingProvider],
        total_deadline_seconds: float,
    ) -> None:
        """接收已校验模型配置、Provider 工厂和一次批量请求的总超时。"""

        self._model_configs = model_configs
        self._default_model_alias = default_model_alias
        self._provider_factory = provider_factory
        self._total_deadline_seconds = total_deadline_seconds

    async def embed(self, request: EmbeddingRequest) -> GatewayEmbeddingResult:
        """
        将一批非空文本转换为等数量、固定维度的向量。

        输入来自同一 DocumentVersion 的一个 Chunk 批次；返回顺序严格对应输入文本。
        Provider 超时、限流或不可用会转换为稳定 AI 异常，业务层无需理解 SDK 异常。
        """

        prepared = self._prepare_provider_call(request)
        try:
            async with asyncio.timeout(self._total_deadline_seconds):
                provider_result = await prepared.provider.embed(
                    prepared.provider_request
                )
        except TimeoutError as error:
            raise AIProviderTimeoutError(
                "Embedding provider request timed out."
            ) from error
        except ProviderError as error:
            raise _translate_provider_error(error) from error

        self._validate_result(
            vectors=provider_result.vectors,
            expected_count=len(request.texts),
            expected_dimension=prepared.dimension,
        )
        return GatewayEmbeddingResult(
            request_id=provider_result.request_id,
            model_alias=prepared.model_alias,
            vectors=provider_result.vectors,
        )

    def _prepare_provider_call(
        self,
        request: EmbeddingRequest,
    ) -> _PreparedEmbeddingCall:
        """选择服务器配置的 Embedding 模型，并构造 Provider 可执行的批量请求。"""

        if not request.texts or any(not text.strip() for text in request.texts):
            raise AIInvalidRequestError("Embedding texts must be non-empty.")

        model_alias = request.model_alias or self._default_model_alias
        if model_alias is None:
            raise AIInvalidModelError("No default embedding model is configured.")

        model_config = self._model_configs.get(model_alias)
        if model_config is None:
            raise AIInvalidModelError("Requested embedding model is not configured.")

        return _PreparedEmbeddingCall(
            model_alias=model_alias,
            dimension=model_config.dimension,
            provider=self._provider_factory(model_config.provider_key),
            provider_request=ProviderEmbeddingRequest(
                request_id=request.request_id,
                texts=request.texts,
                provider_model=model_config.provider_model,
            ),
        )

    @staticmethod
    def _validate_result(
        *,
        vectors: tuple[tuple[float, ...], ...],
        expected_count: int,
        expected_dimension: int,
    ) -> None:
        """确保 Provider 返回与请求一一对应、维度正确且全部为有限数值的向量。"""

        if len(vectors) != expected_count:
            raise AIProviderUnavailableError(
                "Embedding provider returned an unexpected vector count."
            )
        for vector in vectors:
            if len(vector) != expected_dimension:
                raise AIProviderUnavailableError(
                    "Embedding provider returned an unexpected vector dimension."
                )
            if not all(math.isfinite(value) for value in vector):
                raise AIProviderUnavailableError(
                    "Embedding provider returned a non-finite vector value."
                )


def _translate_provider_error(error: ProviderError) -> AIProviderError:
    """将 Provider 的限流、超时和不可用异常转换为业务层稳定 AI 异常。"""

    if isinstance(error, ProviderRateLimitError):
        return AIProviderRateLimitError("Embedding provider rate limit exceeded.")
    if isinstance(error, ProviderTimeoutError):
        return AIProviderTimeoutError("Embedding provider request timed out.")
    if isinstance(error, ProviderUnavailableError):
        return AIProviderUnavailableError("Embedding provider is unavailable.")
    return AIProviderUnavailableError("Embedding provider request failed.")
