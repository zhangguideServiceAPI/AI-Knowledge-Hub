from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import InvalidAccessTokenError
from app.db.redis_client import redis_client
from app.db.repositories.session_repository import SessionRepository
from app.db.session import get_db
from app.schemas.user import UserResponse
from app.services.auth_service import AuthService
from app.services.file_service import FileService
from app.services.login_rate_limiter import LoginRateLimiter
from app.storage.factory import get_storage_bucket, get_storage_provider
from app.storage.provider import StorageProvider
from app.ai.factory import get_chat_provider
from app.ai.gateway import AIGateway
from app.services.chat_service import ChatService

bearer_scheme = HTTPBearer(auto_error=False)


def get_access_token(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> str:
    if credentials is None:
        raise InvalidAccessTokenError()

    return credentials.credentials


def get_session_repository() -> SessionRepository:
    return SessionRepository(redis_client)


def get_current_user(
    token: Annotated[str, Depends(get_access_token)],
    session: Annotated[Session, Depends(get_db)],
) -> UserResponse:
    return AuthService(session).get_current_user(token)


def get_login_rate_limiter() -> LoginRateLimiter:
    return LoginRateLimiter(
        client=redis_client,
        window_seconds=settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS,
        max_attempts=settings.LOGIN_RATE_LIMIT_MAX_ATTEMPTS,
    )


def get_file_service(
    session: Annotated[Session, Depends(get_db)],
    storage_provider: Annotated[StorageProvider, Depends(get_storage_provider)],
) -> FileService:
    return FileService(
        session,
        storage_provider,
        storage_provider_name=settings.STORAGE_PROVIDER,
        bucket=get_storage_bucket(),
        max_upload_size=settings.MAX_UPLOAD_SIZE_BYTES,
        chunk_size=settings.UPLOAD_CHUNK_SIZE_BYTES,
    )


def get_ai_gateway() -> AIGateway:
    return AIGateway(
        model_configs=settings.AI_MODELS,
        default_model_alias=settings.AI_DEFAULT_MODEL_ALIAS,
        provider_factory=get_chat_provider,
        max_retry_attempts=settings.AI_MAX_RETRY_ATTEMPTS,
        retry_backoff_seconds=settings.AI_RETRY_BACKOFF_SECONDS,
        total_deadline_seconds=settings.AI_TOTAL_DEADLINE_SECONDS,
    )


def get_chat_service(
    # FastAPI 先调用 get_ai_gateway()，再把结果注入这个参数。
    gateway: Annotated[AIGateway, Depends(get_ai_gateway)],
) -> ChatService:
    return ChatService(gateway)
