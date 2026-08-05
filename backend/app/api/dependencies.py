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
