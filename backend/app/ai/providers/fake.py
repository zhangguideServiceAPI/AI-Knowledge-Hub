import asyncio
from collections.abc import AsyncIterator

from app.ai.exceptions import ProviderError
from app.ai.provider import (
    ChatEvent,
    ChatResult,
    FinishReason,
    ProviderChatRequest,
    TokenUsage,
)


class FakeChatProvider:
    def __init__(
        self,
        *,
        content: str,
        finish_reason: FinishReason = FinishReason.STOP,
        usage: TokenUsage | None = None,
        generate_error: ProviderError | None = None,
        stream_events: tuple[ChatEvent, ...] = (),
        stream_error: ProviderError | None = None,
        stream_error_after_events: int = 0,  # 输出 N 个 Event 后抛错
        stream_delay_seconds: float = 0.0,
    ) -> None:
        if not 0 <= stream_error_after_events <= len(stream_events):
            raise ValueError(
                "stream_error_after_events must be between zero and "
                "the number of configured stream events."
            )
        if stream_delay_seconds < 0:
            raise ValueError("stream_delay_seconds must not be negative.")

        self.content = content
        self.finish_reason = finish_reason
        self.usage = usage
        self.generate_error = generate_error
        self.last_request: ProviderChatRequest | None = None
        self.stream_events = stream_events
        self.stream_error = stream_error
        self.stream_error_after_events = stream_error_after_events
        self.stream_delay_seconds = stream_delay_seconds
        self.stream_closed = False

    async def generate(self, request: ProviderChatRequest) -> ChatResult:
        self.last_request = request

        if self.generate_error is not None:
            raise self.generate_error

        return ChatResult(
            request_id=request.request_id,
            content=self.content,
            finish_reason=self.finish_reason,
            usage=self.usage,
        )

    async def stream(self, request: ProviderChatRequest) -> AsyncIterator[ChatEvent]:
        self.last_request = request
        self.stream_closed = False
        emitted_count = 0

        try:
            for event in self.stream_events:
                if (
                    self.stream_error is not None
                    and emitted_count == self.stream_error_after_events
                ):
                    raise self.stream_error

                if self.stream_delay_seconds > 0:
                    await asyncio.sleep(self.stream_delay_seconds)

                yield event
                emitted_count += 1

            if (
                self.stream_error is not None
                and emitted_count == self.stream_error_after_events
            ):
                raise self.stream_error
        finally:
            self.stream_closed = True
