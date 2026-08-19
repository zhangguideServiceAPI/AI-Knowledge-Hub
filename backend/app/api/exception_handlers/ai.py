"""AI Gateway 与 PromptCenter 异常的 HTTP 映射。"""

from dataclasses import dataclass

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.ai.exceptions import (
    AIError,
    AIInvalidModelError,
    AIInvalidRequestError,
    AIProviderRateLimitError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
)
from app.ai.prompt_center import PromptError
from app.core.logging import logger
from app.schemas.ai import AIErrorCode, AIErrorResponse


@dataclass(frozen=True)
class PublicAIError:
    """AI 内部异常对外公开时允许携带的 HTTP 状态、错误码和安全文案。"""

    status_code: int
    code: AIErrorCode
    detail: str


# key 是异常类，value 依次是 HTTP 状态码、公共错误码和安全文案。
_AI_ERROR_RESPONSES: dict[
    type[AIError],
    tuple[int, AIErrorCode, str],
] = {
    AIInvalidModelError: (
        status.HTTP_400_BAD_REQUEST,
        AIErrorCode.INVALID_MODEL,
        "Requested AI model is not available.",
    ),
    AIInvalidRequestError: (
        status.HTTP_400_BAD_REQUEST,
        AIErrorCode.INVALID_REQUEST,
        "AI request parameters are invalid.",
    ),
    AIProviderRateLimitError: (
        status.HTTP_429_TOO_MANY_REQUESTS,
        AIErrorCode.PROVIDER_RATE_LIMIT,
        "AI service is temporarily rate limited.",
    ),
    AIProviderTimeoutError: (
        status.HTTP_504_GATEWAY_TIMEOUT,
        AIErrorCode.PROVIDER_TIMEOUT,
        "AI service timed out.",
    ),
    AIProviderUnavailableError: (
        status.HTTP_503_SERVICE_UNAVAILABLE,
        AIErrorCode.PROVIDER_UNAVAILABLE,
        "AI service is temporarily unavailable.",
    ),
}


def map_ai_error(error: AIError) -> PublicAIError:
    """把内部 AIError 映射为稳定的公共状态码、错误码和安全错误文案。"""

    status_code, code, detail = _AI_ERROR_RESPONSES.get(
        type(error),
        (
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            AIErrorCode.INTERNAL_ERROR,
            "AI service failed to process the request.",
        ),
    )
    return PublicAIError(
        status_code=status_code,
        code=code,
        detail=detail,
    )


async def ai_error_handler(
    request: Request,
    error: AIError,
) -> JSONResponse:
    """记录 AI 请求失败的安全字段，并返回标准 AIErrorResponse。"""

    public_error = map_ai_error(error)
    # 只记录固定字段，禁止记录 str(error) 或 Provider 原始异常。
    logger.error(
        "ai.request.failed method=%s path=%s code=%s error_type=%s",
        request.method,
        request.url.path,
        public_error.code.value,
        type(error).__name__,
    )
    response = AIErrorResponse(
        code=public_error.code,
        detail=public_error.detail,
    )
    return JSONResponse(
        status_code=public_error.status_code,
        content=response.model_dump(mode="json"),
    )


async def prompt_error_handler(
    request: Request,
    error: PromptError,
) -> JSONResponse:
    """记录 PromptCenter 失败并返回不包含模板实现细节的通用 AI 错误。"""

    logger.error(
        "ai.prompt.failed method=%s path=%s error_type=%s",
        request.method,
        request.url.path,
        type(error).__name__,
    )
    response = AIErrorResponse(
        code=AIErrorCode.INTERNAL_ERROR,
        detail="AI service failed to process the request.",
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=response.model_dump(mode="json"),
    )


def register_ai_exception_handlers(app: FastAPI) -> None:
    """向 FastAPI 注册 AI Gateway 和 PromptCenter 的异常映射。"""

    app.add_exception_handler(AIError, ai_error_handler)
    app.add_exception_handler(PromptError, prompt_error_handler)
