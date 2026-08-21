import asyncio
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import aclosing
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.ai.exceptions import (
    AIInvalidModelError,
    AIInvalidRequestError,
    AIProviderRateLimitError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
)
from app.ai.gateway import (
    AIGateway,
    ChatRequest as GatewayChatRequest,
)
from app.ai.provider import (
    ChatDelta,
    ChatDone,
    ChatEvent,
    ChatMessage,
    ChatRole,
    ChatUsageEvent,
    FinishReason,
    TokenUsage,
)
from app.ai.prompt_center import PromptCenter, PromptError, RenderedPrompt
from app.ai.usage_cost import calculate_cost_snapshot
from app.core.config import AIModelConfig
from app.core.logging import logger
from app.db.repositories.chat_usage_repository import ChatUsageRepository
from app.models.usage import (
    ChatUsage,
    ChatUsageErrorCode,
    ChatUsageMode,
    ChatUsageStatus,
)
from app.schemas.ai import (
    ChatRequestSchema,
    ChatResponseSchema,
    ChatUsageResponse,
)

_ASSISTANT_PROMPT_KEY = "assistant"
_ASSISTANT_PROMPT_VERSION = "v1"


def _usage_error_code(error: Exception) -> ChatUsageErrorCode:
    """把内部异常转换为可查询且不包含敏感信息的固定错误码。"""

    if isinstance(error, AIInvalidModelError):
        return ChatUsageErrorCode.INVALID_MODEL

    if isinstance(error, AIInvalidRequestError):
        return ChatUsageErrorCode.INVALID_REQUEST

    if isinstance(error, AIProviderRateLimitError):
        return ChatUsageErrorCode.PROVIDER_RATE_LIMIT

    if isinstance(error, AIProviderTimeoutError):
        return ChatUsageErrorCode.PROVIDER_TIMEOUT

    if isinstance(error, AIProviderUnavailableError):
        return ChatUsageErrorCode.PROVIDER_UNAVAILABLE

    if isinstance(error, PromptError):
        return ChatUsageErrorCode.PROMPT_ERROR

    return ChatUsageErrorCode.INTERNAL_ERROR


class ChatService:
    def __init__(
        self,
        gateway: AIGateway,
        prompt_center: PromptCenter,
        *,
        usage_session_factory: Callable[[], Session] | None = None,
        model_configs: Mapping[str, AIModelConfig] | None = None,
        default_model_alias: str | None = None,
    ) -> None:
        self._gateway = gateway
        self._prompt_center = prompt_center
        self._usage_session_factory = usage_session_factory
        self._model_configs = model_configs or {}
        self._default_model_alias = default_model_alias

    def _build_gateway_request(
        self,
        request: ChatRequestSchema,
        *,
        request_id: str,
    ) -> GatewayChatRequest:

        rendered_prompt = self._prompt_center.render(
            prompt_key=_ASSISTANT_PROMPT_KEY,
            version=_ASSISTANT_PROMPT_VERSION,
            variables={},
        )

        return self._build_gateway_request_for_prompt(
            request,
            request_id=request_id,
            rendered_prompt=rendered_prompt,
        )

    def _build_gateway_request_for_prompt(
        self,
        request: ChatRequestSchema,
        *,
        request_id: str,
        rendered_prompt: RenderedPrompt,
    ) -> GatewayChatRequest:
        """将一个已渲染 System Prompt 与受控用户消息组装为 Gateway 请求。"""

        system_message = ChatMessage(
            role=ChatRole.SYSTEM,
            content=rendered_prompt.content,
        )

        # API Message 只包含正文；Service 负责创建受控 USER role。
        user_messages = tuple(
            ChatMessage(
                role=ChatRole.USER,
                content=message.content,
            )
            for message in request.messages
        )
        # 末尾的逗号表示它是只有一个元素的元组。
        messages = (system_message,) + user_messages

        return GatewayChatRequest(
            request_id=request_id,
            messages=messages,
            model_alias=request.model,
            temperature=request.temperature,
            max_output_tokens=request.max_output_tokens,
        )

    async def _save_usage_safely(self, usage: ChatUsage) -> None:
        """在线程中执行同步数据库短事务，避免阻塞异步 Chat 调用链。"""

        await asyncio.to_thread(self._save_usage_in_short_transaction, usage)

    def _save_usage_in_short_transaction(self, usage: ChatUsage) -> None:
        if self._usage_session_factory is None:
            return

        try:
            with self._usage_session_factory() as session:
                try:
                    ChatUsageRepository(session).create(usage)
                    session.commit()
                except SQLAlchemyError:
                    session.rollback()
                    raise
        except SQLAlchemyError:
            # 不记录异常正文，避免数据库驱动信息或敏感参数进入日志。
            logger.error(
                "ai.usage.persist_failed request_id=%s status=%s",
                usage.request_id,
                usage.status,
            )

    async def chat(
        self,
        request: ChatRequestSchema,
        *,
        user_id: int,
    ) -> ChatResponseSchema:
        """使用内置 assistant Prompt 处理一次普通非流式 Chat 请求。"""

        rendered_prompt = self._prompt_center.render(
            prompt_key=_ASSISTANT_PROMPT_KEY,
            version=_ASSISTANT_PROMPT_VERSION,
            variables={},
        )
        return await self.chat_with_rendered_prompt(
            request,
            user_id=user_id,
            rendered_prompt=rendered_prompt,
        )

    async def chat_with_rendered_prompt(
        self,
        request: ChatRequestSchema,
        *,
        user_id: int,
        rendered_prompt: RenderedPrompt,
    ) -> ChatResponseSchema:
        """
        使用调用方已经渲染且校验过的 System Prompt 完成一次非流式 AI 调用。

        普通 Chat 和 RAG 都复用本方法，从而共享 Gateway、Usage、成本和错误处理。调用方
        只能传入 PromptCenter 产出的 `RenderedPrompt`，不能让 Router 直接构造 System
        Message；Usage 会记录真实 Prompt Key/Version，但不会保存 Prompt 或回答正文。
        """

        request_id = str(uuid4())
        created_at = datetime.now(timezone.utc).replace(tzinfo=None)
        started_at = perf_counter()  # 单调递增的高精度计时器，适合计算耗时

        model_alias = request.model or self._default_model_alias

        try:
            gateway_request = self._build_gateway_request_for_prompt(
                request,
                request_id=request_id,
                rendered_prompt=rendered_prompt,
            )
            result = await self._gateway.generate(gateway_request)

        except asyncio.CancelledError:
            await self._save_non_stream_unsuccessful_usage(
                request_id=request_id,
                user_id=user_id,
                model_alias=model_alias,
                created_at=created_at,
                started_at=started_at,
                status=ChatUsageStatus.CANCELLED,
                error_code=ChatUsageErrorCode.CANCELLED,
                prompt_key=rendered_prompt.prompt_key,
                prompt_version=rendered_prompt.version,
            )
            raise

        except Exception as error:
            await self._save_non_stream_unsuccessful_usage(
                request_id=request_id,
                user_id=user_id,
                model_alias=model_alias,
                created_at=created_at,
                started_at=started_at,
                status=ChatUsageStatus.FAILED,
                error_code=_usage_error_code(error),
                prompt_key=rendered_prompt.prompt_key,
                prompt_version=rendered_prompt.version,
            )
            raise

        latency_ms = int((perf_counter() - started_at) * 1000)

        completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        model_config = self._model_configs.get(result.model_alias)
        token_usage = result.usage
        cost_snapshot = calculate_cost_snapshot(
            model_config.pricing if model_config is not None else None,
            token_usage,
        )

        await self._save_usage_safely(
            ChatUsage(
                request_id=result.request_id,
                user_id=user_id,
                request_mode=ChatUsageMode.NON_STREAM.value,
                model_alias=result.model_alias,
                provider=model_config.provider_key if model_config else None,
                provider_model=model_config.provider_model if model_config else None,
                prompt_key=rendered_prompt.prompt_key,
                prompt_version=rendered_prompt.version,
                input_tokens=token_usage.input_tokens if token_usage else None,
                output_tokens=token_usage.output_tokens if token_usage else None,
                total_tokens=token_usage.total_tokens if token_usage else None,
                latency_ms=latency_ms,
                time_to_first_token_ms=None,
                status=ChatUsageStatus.SUCCESS.value,
                finish_reason=result.finish_reason.value,
                error_code=None,
                estimated_cost=(
                    cost_snapshot.estimated_cost if cost_snapshot is not None else None
                ),
                currency=(
                    cost_snapshot.currency if cost_snapshot is not None else None
                ),
                pricing_version=(
                    cost_snapshot.pricing_version if cost_snapshot is not None else None
                ),
                created_at=created_at,
                completed_at=completed_at,
            )
        )

        usage = None
        if result.usage is not None:
            usage = ChatUsageResponse(
                input_tokens=result.usage.input_tokens,
                output_tokens=result.usage.output_tokens,
                total_tokens=result.usage.total_tokens,
            )

        response = ChatResponseSchema(
            request_id=result.request_id,
            model=result.model_alias,
            content=result.content,
            finish_reason=result.finish_reason,
            usage=usage,
        )

        logger.info(
            "ai.chat.success request_id=%s model_alias=%s "
            "total_tokens=%s latency_ms=%s",
            result.request_id,
            result.model_alias,
            usage.total_tokens if usage is not None else None,
            latency_ms,
        )

        return response

    async def _save_non_stream_unsuccessful_usage(
        self,
        *,
        request_id: str,
        user_id: int,
        model_alias: str | None,
        created_at: datetime,
        started_at: float,
        status: ChatUsageStatus,
        error_code: ChatUsageErrorCode,
        prompt_key: str,
        prompt_version: str,
    ) -> None:
        completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        latency_ms = int((perf_counter() - started_at) * 1000)
        model_config = (
            self._model_configs.get(model_alias) if model_alias is not None else None
        )

        await self._save_usage_safely(
            ChatUsage(
                request_id=request_id,
                user_id=user_id,
                request_mode=ChatUsageMode.NON_STREAM.value,
                model_alias=model_alias,
                provider=model_config.provider_key if model_config else None,
                provider_model=model_config.provider_model if model_config else None,
                prompt_key=prompt_key,
                prompt_version=prompt_version,
                input_tokens=None,
                output_tokens=None,
                total_tokens=None,
                latency_ms=latency_ms,
                time_to_first_token_ms=None,
                status=status.value,
                finish_reason=None,
                error_code=error_code.value,
                estimated_cost=None,
                currency=None,
                pricing_version=None,
                created_at=created_at,
                completed_at=completed_at,
            )
        )

    async def stream(
        self,
        request: ChatRequestSchema,
        *,
        user_id: int,
    ) -> AsyncIterator[ChatEvent]:
        request_id = str(uuid4())
        created_at = datetime.now(timezone.utc).replace(tzinfo=None)
        started_at = perf_counter()

        model_alias = request.model or self._default_model_alias
        token_usage: TokenUsage | None = None
        time_to_first_token_ms: int | None = None
        terminal_recorded = False

        try:
            gateway_request = self._build_gateway_request(
                request,
                request_id=request_id,
            )

            async with aclosing(
                self._gateway.stream(gateway_request)
            ) as gateway_stream:
                async for event in gateway_stream:
                    if isinstance(event, ChatDelta) and time_to_first_token_ms is None:
                        time_to_first_token_ms = int(
                            (perf_counter() - started_at) * 1000
                        )

                    elif isinstance(event, ChatUsageEvent):
                        token_usage = event.usage

                    elif isinstance(event, ChatDone):
                        await self._record_stream_success(
                            request_id=request_id,
                            user_id=user_id,
                            model_alias=model_alias,
                            token_usage=token_usage,
                            finish_reason=event.finish_reason,
                            created_at=created_at,
                            started_at=started_at,
                            time_to_first_token_ms=time_to_first_token_ms,
                        )
                        terminal_recorded = True

                    yield event

        except asyncio.CancelledError:
            if not terminal_recorded:
                await self._record_stream_unsuccessful(
                    request_id=request_id,
                    user_id=user_id,
                    model_alias=model_alias,
                    token_usage=token_usage,
                    created_at=created_at,
                    started_at=started_at,
                    time_to_first_token_ms=time_to_first_token_ms,
                    status=ChatUsageStatus.CANCELLED,
                    error_code=ChatUsageErrorCode.CANCELLED,
                )
            raise

        except GeneratorExit:
            if not terminal_recorded:
                await self._record_stream_unsuccessful(
                    request_id=request_id,
                    user_id=user_id,
                    model_alias=model_alias,
                    token_usage=token_usage,
                    created_at=created_at,
                    started_at=started_at,
                    time_to_first_token_ms=time_to_first_token_ms,
                    status=ChatUsageStatus.CANCELLED,
                    error_code=ChatUsageErrorCode.CANCELLED,
                )
            raise

        except Exception as error:
            if not terminal_recorded:
                await self._record_stream_unsuccessful(
                    request_id=request_id,
                    user_id=user_id,
                    model_alias=model_alias,
                    token_usage=token_usage,
                    created_at=created_at,
                    started_at=started_at,
                    time_to_first_token_ms=time_to_first_token_ms,
                    status=ChatUsageStatus.FAILED,
                    error_code=_usage_error_code(error),
                )
            raise

    async def _record_stream_success(
        self,
        *,
        request_id: str,
        user_id: int,
        model_alias: str | None,
        token_usage: TokenUsage | None,
        finish_reason: FinishReason,
        created_at: datetime,
        started_at: float,
        time_to_first_token_ms: int | None,
    ) -> None:
        completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        latency_ms = int((perf_counter() - started_at) * 1000)

        model_config = (
            self._model_configs.get(model_alias) if model_alias is not None else None
        )
        cost_snapshot = calculate_cost_snapshot(
            model_config.pricing if model_config is not None else None,
            token_usage,
        )

        await self._save_usage_safely(
            ChatUsage(
                request_id=request_id,
                user_id=user_id,
                request_mode=ChatUsageMode.STREAM.value,
                model_alias=model_alias,
                provider=model_config.provider_key if model_config else None,
                provider_model=model_config.provider_model if model_config else None,
                prompt_key=_ASSISTANT_PROMPT_KEY,
                prompt_version=_ASSISTANT_PROMPT_VERSION,
                input_tokens=(
                    token_usage.input_tokens if token_usage is not None else None
                ),
                output_tokens=(
                    token_usage.output_tokens if token_usage is not None else None
                ),
                total_tokens=(
                    token_usage.total_tokens if token_usage is not None else None
                ),
                latency_ms=latency_ms,
                time_to_first_token_ms=time_to_first_token_ms,
                status=ChatUsageStatus.SUCCESS.value,
                finish_reason=finish_reason.value,
                error_code=None,
                estimated_cost=(
                    cost_snapshot.estimated_cost if cost_snapshot is not None else None
                ),
                currency=(
                    cost_snapshot.currency if cost_snapshot is not None else None
                ),
                pricing_version=(
                    cost_snapshot.pricing_version if cost_snapshot is not None else None
                ),
                created_at=created_at,
                completed_at=completed_at,
            )
        )

        logger.info(
            "ai.chat.stream.success request_id=%s model_alias=%s "
            "total_tokens=%s latency_ms=%s ttft_ms=%s",
            request_id,
            model_alias,
            token_usage.total_tokens if token_usage is not None else None,
            latency_ms,
            time_to_first_token_ms,
        )

    async def _record_stream_unsuccessful(
        self,
        *,
        request_id: str,
        user_id: int,
        model_alias: str | None,
        token_usage: TokenUsage | None,
        created_at: datetime,
        started_at: float,
        time_to_first_token_ms: int | None,
        status: ChatUsageStatus,
        error_code: ChatUsageErrorCode,
    ) -> None:
        completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        latency_ms = int((perf_counter() - started_at) * 1000)

        model_config = (
            self._model_configs.get(model_alias) if model_alias is not None else None
        )
        cost_snapshot = calculate_cost_snapshot(
            model_config.pricing if model_config is not None else None,
            token_usage,
        )

        await self._save_usage_safely(
            ChatUsage(
                request_id=request_id,
                user_id=user_id,
                request_mode=ChatUsageMode.STREAM.value,
                model_alias=model_alias,
                provider=model_config.provider_key if model_config else None,
                provider_model=model_config.provider_model if model_config else None,
                prompt_key=_ASSISTANT_PROMPT_KEY,
                prompt_version=_ASSISTANT_PROMPT_VERSION,
                input_tokens=(
                    token_usage.input_tokens if token_usage is not None else None
                ),
                output_tokens=(
                    token_usage.output_tokens if token_usage is not None else None
                ),
                total_tokens=(
                    token_usage.total_tokens if token_usage is not None else None
                ),
                latency_ms=latency_ms,
                time_to_first_token_ms=time_to_first_token_ms,
                status=status.value,
                finish_reason=None,
                error_code=error_code.value,
                estimated_cost=(
                    cost_snapshot.estimated_cost if cost_snapshot is not None else None
                ),
                currency=(
                    cost_snapshot.currency if cost_snapshot is not None else None
                ),
                pricing_version=(
                    cost_snapshot.pricing_version if cost_snapshot is not None else None
                ),
                created_at=created_at,
                completed_at=completed_at,
            )
        )

        logger.info(
            "ai.chat.stream.terminal request_id=%s model_alias=%s "
            "status=%s error_code=%s latency_ms=%s "
            "ttft_ms=%s",
            request_id,
            model_alias,
            status.value,
            error_code.value,
            latency_ms,
            time_to_first_token_ms,
        )
