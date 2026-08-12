import asyncio
import json
from collections.abc import AsyncIterator

import pytest

from app.ai.exceptions import (
    AIError,
    AIInvalidModelError,
    AIInvalidRequestError,
    AIProviderRateLimitError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
)
from app.ai.provider import (
    ChatDelta,
    ChatDone,
    ChatUsageEvent,
    FinishReason,
    TokenUsage,
)
from app.api.ai_sse import (
    encode_chat_error,
    encode_chat_event,
    encode_started_chat_stream,
)


def _parse_sse_frame(frame: str) -> tuple[str, dict[str, object]]:
    assert frame.endswith("\n\n")
    assert not frame.endswith("\n\n\n")

    lines = frame.removesuffix("\n\n").splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("event: ")
    assert lines[1].startswith("data: ")

    event_name = lines[0].removeprefix("event: ")
    data = json.loads(lines[1].removeprefix("data: "))
    return event_name, data


async def _collect_frames(stream: AsyncIterator[str]) -> list[str]:
    return [frame async for frame in stream]


async def _event_stream(
    events: tuple[ChatDelta | ChatUsageEvent | ChatDone, ...],
    *,
    error: AIError | None = None,
    closed: list[bool] | None = None,
) -> AsyncIterator[ChatDelta | ChatUsageEvent | ChatDone]:
    try:
        for event in events:
            yield event

        if error is not None:
            raise error
    finally:
        if closed is not None:
            closed.append(True)


def test_encode_delta_as_single_sse_frame_with_escaped_content() -> None:
    frame = encode_chat_event(
        ChatDelta(
            request_id="request-1",
            content='第一行\n第二行 "quoted"',
        )
    )

    event_name, data = _parse_sse_frame(frame)

    assert event_name == "delta"
    assert data == {
        "request_id": "request-1",
        "content": '第一行\n第二行 "quoted"',
    }
    # JSON 中的正文换行必须被转义，不能拆断 SSE data 行。
    assert "第一行\\n第二行" in frame


@pytest.mark.parametrize(
    ("usage", "expected_data"),
    [
        (
            TokenUsage(
                input_tokens=10,
                output_tokens=20,
                total_tokens=30,
            ),
            {
                "request_id": "request-1",
                "input_tokens": 10,
                "output_tokens": 20,
                "total_tokens": 30,
            },
        ),
        (
            TokenUsage(
                input_tokens=None,
                output_tokens=None,
                total_tokens=None,
            ),
            {
                "request_id": "request-1",
                "input_tokens": None,
                "output_tokens": None,
                "total_tokens": None,
            },
        ),
    ],
)
def test_encode_usage_preserves_known_and_unknown_token_counts(
    usage: TokenUsage,
    expected_data: dict[str, object],
) -> None:
    frame = encode_chat_event(
        ChatUsageEvent(
            request_id="request-1",
            usage=usage,
        )
    )

    event_name, data = _parse_sse_frame(frame)

    assert event_name == "usage"
    assert data == expected_data


@pytest.mark.parametrize(
    "finish_reason",
    [
        FinishReason.STOP,
        FinishReason.LENGTH,
        FinishReason.CONTENT_FILTER,
    ],
)
def test_encode_done_uses_stable_finish_reason(
    finish_reason: FinishReason,
) -> None:
    frame = encode_chat_event(
        ChatDone(
            request_id="request-1",
            finish_reason=finish_reason,
        )
    )

    event_name, data = _parse_sse_frame(frame)

    assert event_name == "done"
    assert data == {
        "request_id": "request-1",
        "finish_reason": finish_reason.value,
    }


def test_encode_rejects_unsupported_runtime_event() -> None:
    with pytest.raises(TypeError, match="Unsupported chat stream event"):
        encode_chat_event(object())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("error", "expected_code", "expected_detail"),
    [
        (
            AIInvalidModelError("raw provider model detail"),
            "ai_invalid_model",
            "Requested AI model is not available.",
        ),
        (
            AIInvalidRequestError("raw invalid request detail"),
            "ai_invalid_request",
            "AI request parameters are invalid.",
        ),
        (
            AIProviderRateLimitError("raw provider rate-limit detail"),
            "ai_provider_rate_limit",
            "AI service is temporarily rate limited.",
        ),
        (
            AIProviderTimeoutError("raw provider timeout detail"),
            "ai_provider_timeout",
            "AI service timed out.",
        ),
        (
            AIProviderUnavailableError("raw provider unavailable detail"),
            "ai_provider_unavailable",
            "AI service is temporarily unavailable.",
        ),
    ],
)
def test_encode_error_uses_stable_public_code_and_detail(
    error: AIError,
    expected_code: str,
    expected_detail: str,
) -> None:
    frame = encode_chat_error(error)

    event_name, data = _parse_sse_frame(frame)

    assert event_name == "error"
    assert data == {
        "code": expected_code,
        "detail": expected_detail,
    }
    assert str(error) not in frame
    assert "status_code" not in frame


def test_encode_error_uses_safe_fallback_without_leaking_internal_detail() -> None:
    class FutureAIError(AIError):
        pass

    sensitive_detail = (
        "provider=https://private-provider.example "
        "model=secret-provider-model sdk_error=raw-native-response"
    )

    frame = encode_chat_error(FutureAIError(sensitive_detail))

    event_name, data = _parse_sse_frame(frame)

    assert event_name == "error"
    assert data == {
        "code": "ai_internal_error",
        "detail": "AI service failed to process the request.",
    }
    assert sensitive_detail not in frame
    assert "private-provider" not in frame
    assert "secret-provider-model" not in frame
    assert "raw-native-response" not in frame


def test_started_stream_yields_prefetched_event_then_remaining_events() -> None:
    first_event = ChatDelta(request_id="request-1", content="First")
    remaining_events = (
        ChatDelta(request_id="request-1", content=" second"),
        ChatUsageEvent(
            request_id="request-1",
            usage=TokenUsage(
                input_tokens=4,
                output_tokens=2,
                total_tokens=6,
            ),
        ),
        ChatDone(
            request_id="request-1",
            finish_reason=FinishReason.STOP,
        ),
    )
    closed: list[bool] = []

    frames = asyncio.run(
        _collect_frames(
            encode_started_chat_stream(
                first_event,
                _event_stream(remaining_events, closed=closed),
            )
        )
    )

    parsed_frames = [_parse_sse_frame(frame) for frame in frames]
    assert [event_name for event_name, _ in parsed_frames] == [
        "delta",
        "delta",
        "usage",
        "done",
    ]
    assert parsed_frames[0][1]["content"] == "First"
    assert parsed_frames[1][1]["content"] == " second"
    assert closed == [True]


def test_started_stream_stops_and_closes_source_after_done() -> None:
    first_event = ChatDelta(request_id="request-1", content="visible")
    done = ChatDone(
        request_id="request-1",
        finish_reason=FinishReason.STOP,
    )
    trailing_event = ChatDelta(
        request_id="request-1",
        content="must not be emitted",
    )
    closed: list[bool] = []

    frames = asyncio.run(
        _collect_frames(
            encode_started_chat_stream(
                first_event,
                _event_stream((done, trailing_event), closed=closed),
            )
        )
    )

    parsed_frames = [_parse_sse_frame(frame) for frame in frames]
    assert [event_name for event_name, _ in parsed_frames] == ["delta", "done"]
    assert "must not be emitted" not in "".join(frames)
    assert closed == [True]


def test_started_stream_converts_ai_error_after_first_event_and_closes() -> None:
    private_detail = "raw provider timeout with private endpoint"
    closed: list[bool] = []

    frames = asyncio.run(
        _collect_frames(
            encode_started_chat_stream(
                ChatDelta(request_id="request-1", content="visible"),
                _event_stream(
                    (),
                    error=AIProviderTimeoutError(private_detail),
                    closed=closed,
                ),
            )
        )
    )

    parsed_frames = [_parse_sse_frame(frame) for frame in frames]
    assert parsed_frames == [
        (
            "delta",
            {"request_id": "request-1", "content": "visible"},
        ),
        (
            "error",
            {
                "code": "ai_provider_timeout",
                "detail": "AI service timed out.",
            },
        ),
    ]
    assert private_detail not in "".join(frames)
    assert closed == [True]
