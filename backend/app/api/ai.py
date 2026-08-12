import asyncio
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import StreamingResponse

from app.ai.exceptions import AIProviderUnavailableError
from app.ai.provider import ChatEvent
from app.api.ai_sse import encode_started_chat_stream
from app.api.dependencies import get_chat_service, get_current_user
from app.schemas.ai import (
    AIErrorResponse,
    ChatRequestSchema,
    ChatResponseSchema,
)
from app.schemas.error import ErrorResponse
from app.schemas.user import UserResponse
from app.services.chat_service import ChatService


router = APIRouter(
    prefix="/ai",
    tags=["AI"],
)


@router.post(
    "/chat",
    response_model=ChatResponseSchema,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "model": AIErrorResponse,
            "description": "Invalid AI model or generation parameters.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponse,
            "description": "Invalid or missing access token.",
        },
        status.HTTP_403_FORBIDDEN: {
            "model": ErrorResponse,
            "description": "User account is inactive.",
        },
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "model": AIErrorResponse,
            "description": "AI provider is temporarily rate limited.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": AIErrorResponse,
            "description": "Unexpected AI service failure.",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": AIErrorResponse,
            "description": "AI service is temporarily unavailable.",
        },
        status.HTTP_504_GATEWAY_TIMEOUT: {
            "model": AIErrorResponse,
            "description": "AI service timed out.",
        },
    },
)
async def chat(
    request: ChatRequestSchema,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
) -> ChatResponseSchema:
    return await chat_service.chat(
        request,
        user_id=current_user.id,
    )


@router.post(
    "/chat/stream",
    response_class=StreamingResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "model": AIErrorResponse,
            "description": "Invalid AI model or generation parameters.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponse,
            "description": "Invalid or missing access token.",
        },
        status.HTTP_403_FORBIDDEN: {
            "model": ErrorResponse,
            "description": "User account is inactive.",
        },
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "model": AIErrorResponse,
            "description": "AI provider is temporarily rate limited.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": AIErrorResponse,
            "description": "Unexpected AI service failure.",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": AIErrorResponse,
            "description": "AI service is temporarily unavailable.",
        },
        status.HTTP_504_GATEWAY_TIMEOUT: {
            "model": AIErrorResponse,
            "description": "AI service timed out.",
        },
    },
)
async def stream_chat(
    request: ChatRequestSchema,
    http_request: Request,
    current_user: Annotated[
        UserResponse,
        Depends(get_current_user),
    ],
    chat_service: Annotated[
        ChatService,
        Depends(get_chat_service),
    ],
) -> StreamingResponse:
    service_stream = chat_service.stream(
        request,
        user_id=current_user.id,
    )

    try:
        # 预取成功前不创建 StreamingResponse，因此仍可返回非 200 错误。
        first_event = await _prefetch_first_event(
            http_request,
            service_stream,
        )
    except StopAsyncIteration as error:
        await service_stream.aclose()
        raise AIProviderUnavailableError(
            "AI stream ended before the first event."
        ) from error
    except BaseException:
        await service_stream.aclose()
        raise

    return StreamingResponse(
        encode_started_chat_stream(
            first_event,
            service_stream,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _wait_for_disconnect(request: Request) -> None:
    while True:
        message = await request.receive()

        if message["type"] == "http.disconnect":
            return


async def _prefetch_first_event(
    request: Request,
    stream: AsyncIterator[ChatEvent],
) -> ChatEvent:
    first_event_task = asyncio.create_task(anext(stream))
    disconnect_task = asyncio.create_task(_wait_for_disconnect(request))
    tasks = (first_event_task, disconnect_task)

    try:
        done, _ = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED,
        )

        if disconnect_task in done:
            # 如果 receive() 自身异常，在这里原样抛出。
            await disconnect_task
            raise asyncio.CancelledError()

        return await first_event_task
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()

        # return_exceptions=True 只负责回收 Task；上面的 await 已经决定
        # 哪个业务结果或异常需要向 Router 传播。
        await asyncio.gather(*tasks, return_exceptions=True)
