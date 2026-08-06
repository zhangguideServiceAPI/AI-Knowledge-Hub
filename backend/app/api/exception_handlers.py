from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError

from app.core.exceptions import (
    EmailAlreadyRegisteredError,
    InactiveUserError,
    InvalidAccessTokenError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    LoginRateLimitExceededError,
)
from app.core.logging import logger
from app.schemas.error import ErrorResponse


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
