from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from dataclasses import dataclass

from app.ai.exceptions import (
    AIError,
    AIInvalidModelError,
    AIInvalidRequestError,
    AIProviderRateLimitError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
)
from app.core.exceptions import (
    EmailAlreadyRegisteredError,
    InactiveUserError,
    InvalidAccessTokenError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    LoginRateLimitExceededError,
    UserSessionNotFoundError,
)
from app.core.logging import logger
from app.schemas.ai import AIErrorCode, AIErrorResponse
from app.schemas.error import ErrorResponse
from app.storage.exceptions import (
    EmptyFileError,
    FileContentUnavailableError,
    FileDeleteFailedError,
    FileResourceNotFoundError,
    FileTooLargeError,
    FileUploadFailedError,
    InvalidFileNameError,
    StorageUnavailableError,
    UnsupportedFileTypeError,
)


async def email_already_registered_handler(
    _request: Request,
    _error: EmailAlreadyRegisteredError,
) -> JSONResponse:
    response = ErrorResponse(
        detail="Email is already registered.",
    )
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content=response.model_dump(),
    )


async def invalid_credentials_handler(
    _request: Request,
    _error: InvalidCredentialsError,
) -> JSONResponse:
    response = ErrorResponse(
        detail="Invalid email or password.",
    )
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content=response.model_dump(),
        headers={"WWW-Authenticate": "Bearer"},
    )


async def invalid_access_token_handler(
    _request: Request,
    _error: InvalidAccessTokenError,
) -> JSONResponse:
    response = ErrorResponse(
        detail="Invalid or missing access token.",
    )
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content=response.model_dump(),
        headers={"WWW-Authenticate": "Bearer"},
    )


async def login_rate_limit_exceeded_handler(
    _request: Request,
    _error: LoginRateLimitExceededError,
) -> JSONResponse:
    response = ErrorResponse(
        detail="Too many login attempts. Try again later.",
    )
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content=response.model_dump(),
    )


async def redis_unavailable_handler(
    request: Request,
    error: RedisError,
) -> JSONResponse:
    logger.error(
        "auth.redis.unavailable method=%s path=%s error_type=%s",
        request.method,
        request.url.path,
        type(error).__name__,
    )
    response = ErrorResponse(
        detail="Authentication service is temporarily unavailable.",
    )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=response.model_dump(),
    )


async def inactive_user_handler(
    _request: Request,
    _error: InactiveUserError,
) -> JSONResponse:
    response = ErrorResponse(
        detail="User account is inactive.",
    )
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content=response.model_dump(),
    )


async def invalid_refresh_token_handler(
    _request: Request,
    _error: InvalidRefreshTokenError,
) -> JSONResponse:
    response = ErrorResponse(
        detail="Invalid or expired refresh token.",
    )
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content=response.model_dump(),
    )


async def user_session_not_found_handler(
    _request: Request,
    _error: UserSessionNotFoundError,
) -> JSONResponse:
    response = ErrorResponse(
        detail="Session not found.",
    )
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=response.model_dump(),
    )


async def invalid_upload_metadata_handler(
    _request: Request,
    _error: InvalidFileNameError | EmptyFileError,
) -> JSONResponse:
    response = ErrorResponse(detail="Invalid upload metadata.")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=response.model_dump(),
    )


async def file_too_large_handler(
    _request: Request,
    _error: FileTooLargeError,
) -> JSONResponse:
    response = ErrorResponse(detail="Uploaded file is too large.")
    return JSONResponse(
        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        content=response.model_dump(),
    )


async def unsupported_file_type_handler(
    _request: Request,
    _error: UnsupportedFileTypeError,
) -> JSONResponse:
    response = ErrorResponse(detail="Unsupported file type.")
    return JSONResponse(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        content=response.model_dump(),
    )


async def storage_unavailable_handler(
    request: Request,
    _error: StorageUnavailableError,
) -> JSONResponse:
    logger.error(
        "storage.provider.unavailable method=%s path=%s",
        request.method,
        request.url.path,
    )
    response = ErrorResponse(detail="File storage is temporarily unavailable.")
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=response.model_dump(),
    )


async def file_upload_failed_handler(
    request: Request,
    _error: FileUploadFailedError,
) -> JSONResponse:
    logger.error(
        "storage.upload.failed method=%s path=%s",
        request.method,
        request.url.path,
    )
    response = ErrorResponse(detail="File upload failed.")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=response.model_dump(),
    )


async def file_resource_not_found_handler(
    _request: Request,
    _error: FileResourceNotFoundError,
) -> JSONResponse:
    response = ErrorResponse(detail="File not found.")
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=response.model_dump(),
    )


async def file_delete_failed_handler(
    request: Request,
    _error: FileDeleteFailedError,
) -> JSONResponse:
    logger.error(
        "storage.delete.failed method=%s path=%s",
        request.method,
        request.url.path,
    )
    response = ErrorResponse(detail="File deletion failed.")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=response.model_dump(),
    )


async def file_content_unavailable_handler(
    request: Request,
    _error: FileContentUnavailableError,
) -> JSONResponse:
    logger.error(
        "storage.download.failed method=%s path=%s",
        request.method,
        request.url.path,
    )
    response = ErrorResponse(detail="File content is unavailable.")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=response.model_dump(),
    )


@dataclass(frozen=True)
class PublicAIError:
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


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(
        EmailAlreadyRegisteredError,
        email_already_registered_handler,
    )
    app.add_exception_handler(
        InvalidCredentialsError,
        invalid_credentials_handler,
    )
    app.add_exception_handler(
        InvalidAccessTokenError,
        invalid_access_token_handler,
    )
    app.add_exception_handler(
        InvalidRefreshTokenError,
        invalid_refresh_token_handler,
    )
    app.add_exception_handler(
        LoginRateLimitExceededError,
        login_rate_limit_exceeded_handler,
    )
    app.add_exception_handler(
        RedisError,
        redis_unavailable_handler,
    )
    app.add_exception_handler(
        InactiveUserError,
        inactive_user_handler,
    )
    app.add_exception_handler(
        UserSessionNotFoundError,
        user_session_not_found_handler,
    )
    app.add_exception_handler(InvalidFileNameError, invalid_upload_metadata_handler)
    app.add_exception_handler(EmptyFileError, invalid_upload_metadata_handler)
    app.add_exception_handler(FileTooLargeError, file_too_large_handler)
    app.add_exception_handler(UnsupportedFileTypeError, unsupported_file_type_handler)
    app.add_exception_handler(StorageUnavailableError, storage_unavailable_handler)
    app.add_exception_handler(FileUploadFailedError, file_upload_failed_handler)
    app.add_exception_handler(
        FileResourceNotFoundError, file_resource_not_found_handler
    )
    app.add_exception_handler(FileDeleteFailedError, file_delete_failed_handler)
    app.add_exception_handler(
        FileContentUnavailableError,
        file_content_unavailable_handler,
    )
    app.add_exception_handler(AIError, ai_error_handler)
