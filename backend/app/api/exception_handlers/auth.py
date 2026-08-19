"""认证、用户 Session 与 Redis 相关异常的 HTTP 映射。"""

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
    UserSessionNotFoundError,
)
from app.core.logging import logger
from app.schemas.error import ErrorResponse


async def email_already_registered_handler(
    _request: Request,
    _error: EmailAlreadyRegisteredError,
) -> JSONResponse:
    """将重复注册邮箱转换为不泄露内部信息的 409 响应。"""

    response = ErrorResponse(detail="Email is already registered.")
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content=response.model_dump(),
    )


async def invalid_credentials_handler(
    _request: Request,
    _error: InvalidCredentialsError,
) -> JSONResponse:
    """将错误邮箱或密码转换为带 Bearer 提示的 401 响应。"""

    response = ErrorResponse(detail="Invalid email or password.")
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content=response.model_dump(),
        headers={"WWW-Authenticate": "Bearer"},
    )


async def invalid_access_token_handler(
    _request: Request,
    _error: InvalidAccessTokenError,
) -> JSONResponse:
    """将缺失或失效 Access Token 转换为带 Bearer 提示的 401 响应。"""

    response = ErrorResponse(detail="Invalid or missing access token.")
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content=response.model_dump(),
        headers={"WWW-Authenticate": "Bearer"},
    )


async def login_rate_limit_exceeded_handler(
    _request: Request,
    _error: LoginRateLimitExceededError,
) -> JSONResponse:
    """将登录频率限制异常转换为 429 响应。"""

    response = ErrorResponse(detail="Too many login attempts. Try again later.")
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content=response.model_dump(),
    )


async def redis_unavailable_handler(
    request: Request,
    error: RedisError,
) -> JSONResponse:
    """记录 Redis 不可用的请求上下文，并返回认证服务暂不可用的 503。"""

    logger.error(
        "auth.redis.unavailable method=%s path=%s error_type=%s",
        request.method,
        request.url.path,
        type(error).__name__,
    )
    response = ErrorResponse(
        detail="Authentication service is temporarily unavailable."
    )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=response.model_dump(),
    )


async def inactive_user_handler(
    _request: Request,
    _error: InactiveUserError,
) -> JSONResponse:
    """将已停用账号的访问转换为 403 响应。"""

    response = ErrorResponse(detail="User account is inactive.")
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content=response.model_dump(),
    )


async def invalid_refresh_token_handler(
    _request: Request,
    _error: InvalidRefreshTokenError,
) -> JSONResponse:
    """将失效 Refresh Token 转换为 401 响应。"""

    response = ErrorResponse(detail="Invalid or expired refresh token.")
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content=response.model_dump(),
    )


async def user_session_not_found_handler(
    _request: Request,
    _error: UserSessionNotFoundError,
) -> JSONResponse:
    """将不存在的用户 Session 转换为 404 响应。"""

    response = ErrorResponse(detail="Session not found.")
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=response.model_dump(),
    )


def register_auth_exception_handlers(app: FastAPI) -> None:
    """向 FastAPI 注册认证和 Session 领域的全部异常映射。"""

    app.add_exception_handler(
        EmailAlreadyRegisteredError, email_already_registered_handler
    )
    app.add_exception_handler(InvalidCredentialsError, invalid_credentials_handler)
    app.add_exception_handler(InvalidAccessTokenError, invalid_access_token_handler)
    app.add_exception_handler(InvalidRefreshTokenError, invalid_refresh_token_handler)
    app.add_exception_handler(
        LoginRateLimitExceededError,
        login_rate_limit_exceeded_handler,
    )
    app.add_exception_handler(RedisError, redis_unavailable_handler)
    app.add_exception_handler(InactiveUserError, inactive_user_handler)
    app.add_exception_handler(UserSessionNotFoundError, user_session_not_found_handler)
