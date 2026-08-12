from collections.abc import AsyncIterator
from contextlib import aclosing

from app.ai.provider import (
    ChatDelta,
    ChatDone,
    ChatEvent,
    ChatUsageEvent,
)
from app.schemas.ai import (
    ChatStreamDeltaData,
    ChatStreamDoneData,
    ChatStreamUsageData,
    ChatStreamErrorData,
)
from app.ai.exceptions import AIError
from app.api.exception_handlers import map_ai_error


def encode_chat_event(event: ChatEvent) -> str:
    if isinstance(event, ChatDelta):
        event_name = "delta"
        data = ChatStreamDeltaData(
            request_id=event.request_id,
            content=event.content,
        )

    elif isinstance(event, ChatUsageEvent):
        event_name = "usage"
        data = ChatStreamUsageData(
            request_id=event.request_id,
            input_tokens=event.usage.input_tokens,
            output_tokens=event.usage.output_tokens,
            total_tokens=event.usage.total_tokens,
        )

    elif isinstance(event, ChatDone):
        event_name = "done"
        data = ChatStreamDoneData(
            request_id=event.request_id,
            finish_reason=event.finish_reason,
        )

    else:
        raise TypeError("Unsupported chat stream event.")

    return f"event: {event_name}\ndata: {data.model_dump_json()}\n\n"


def encode_chat_error(error: AIError) -> str:
    public_error = map_ai_error(error)
    data = ChatStreamErrorData(
        code=public_error.code,
        detail=public_error.detail,
    )

    return f"event: error\ndata: {data.model_dump_json()}\n\n"


async def encode_started_chat_stream(
    first_event: ChatEvent,
    stream: AsyncIterator[ChatEvent],
) -> AsyncIterator[str]:
    async with aclosing(stream):
        yield encode_chat_event(first_event)

        if isinstance(first_event, ChatDone):
            return

        try:
            async for event in stream:
                yield encode_chat_event(event)

                # done 是成功终态，不能再出现 error 或其他 Event。
                if isinstance(event, ChatDone):
                    return
        except AIError as error:
            # HTTP 200 已经发出，只能返回安全 error Event。
            yield encode_chat_error(error)
