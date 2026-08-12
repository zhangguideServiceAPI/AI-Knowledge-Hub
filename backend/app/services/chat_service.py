from time import perf_counter
from uuid import uuid4
from collections.abc import AsyncIterator
from contextlib import aclosing

from app.ai.gateway import (
    AIGateway,
    ChatRequest as GatewayChatRequest,
)
from app.core.logging import logger
from app.schemas.ai import (
    ChatRequestSchema,
    ChatResponseSchema,
    ChatUsageResponse,
)
from app.ai.provider import (
    ChatEvent,
    ChatMessage,
    ChatRole,
)


def _build_gateway_request(
    request: ChatRequestSchema,
    *,
    request_id: str,
) -> GatewayChatRequest:

    # API Message 只包含正文；Service 负责创建受控 USER role。
    messages = tuple(
        ChatMessage(
            role=ChatRole.USER,
            content=message.content,
        )
        for message in request.messages
    )

    return GatewayChatRequest(
        request_id=request_id,
        messages=messages,
        model_alias=request.model,
        temperature=request.temperature,
        max_output_tokens=request.max_output_tokens,
    )


class ChatService:
    def __init__(self, gateway: AIGateway) -> None:
        self._gateway = gateway

    async def chat(
        self,
        request: ChatRequestSchema,
        *,
        user_id: int,
    ) -> ChatResponseSchema:
        request_id = str(uuid4())

        gateway_request = _build_gateway_request(request, request_id=request_id)

        started_at = perf_counter()  # 单调递增的高精度计时器，适合计算耗时
        result = await self._gateway.generate(gateway_request)
        latency_ms = int((perf_counter() - started_at) * 1000)

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
            "ai.chat.success request_id=%s user_id=%s "
            "model_alias=%s total_tokens=%s latency_ms=%s",
            result.request_id,
            user_id,
            result.model_alias,
            usage.total_tokens if usage is not None else None,
            latency_ms,
        )

        return response

    async def stream(
        self,
        request: ChatRequestSchema,
        *,
        user_id: int,
    ) -> AsyncIterator[ChatEvent]:
        request_id = str(uuid4())
        gateway_request = _build_gateway_request(
            request,
            request_id=request_id,
        )

        # user_id 会在 Story 4.8 用于记录 Streaming Usage 终态。
        # 当前 Story 先建立认证业务边界，不在这里提前写数据库。
        _ = user_id

        async with aclosing(self._gateway.stream(gateway_request)) as gateway_stream:
            async for event in gateway_stream:
                yield event
