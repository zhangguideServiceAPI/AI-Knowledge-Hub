from time import perf_counter
from uuid import uuid4

from app.ai.gateway import (
    AIGateway,
    ChatRequest as GatewayChatRequest,
)
from app.ai.provider import ChatMessage, ChatRole
from app.core.logging import logger
from app.schemas.ai import (
    ChatRequestSchema,
    ChatResponseSchema,
    ChatUsageResponse,
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

        # API Message 只包含正文；Service 负责创建受控 USER role。
        messages = tuple(
            ChatMessage(
                role=ChatRole.USER,
                content=message.content,
            )
            for message in request.messages
        )

        gateway_request = GatewayChatRequest(
            request_id=request_id,
            messages=messages,
            model_alias=request.model,
            temperature=request.temperature,
            max_output_tokens=request.max_output_tokens,
        )

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
