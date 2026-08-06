from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_login_rate_limiter, get_session_repository
from app.db.repositories.session_repository import SessionRepository
from app.db.session import get_db
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPairResponse,
)
from app.schemas.error import ErrorResponse
from app.schemas.user import UserResponse
from app.services.auth_service import AuthService
from app.services.login_rate_limiter import LoginRateLimiter

router = APIRouter(
    prefix="/auth",
    tags=["Auth"],
)


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "Email is already registered.",
        },
    },
)
def register(
    request: RegisterRequest,
    session: Annotated[Session, Depends(get_db)],
) -> UserResponse:
    return AuthService(session).register(request)


@router.post(
    "/login",
    response_model=TokenPairResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponse,
            "description": "Invalid email or password.",
        },
        status.HTTP_403_FORBIDDEN: {
            "model": ErrorResponse,
            "description": "User account is inactive.",
        },
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "model": ErrorResponse,
            "description": "Too many login attempts.",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "Authentication service is temporarily unavailable.",
        },
    },
)
def login(
    request: LoginRequest,
    session: Annotated[Session, Depends(get_db)],
    rate_limiter: Annotated[
        LoginRateLimiter,
        Depends(get_login_rate_limiter),
    ],
    session_repository: Annotated[
        SessionRepository,
        Depends(get_session_repository),
    ],
) -> TokenPairResponse:
    return AuthService(session).login(request, rate_limiter, session_repository)


@router.post(
    "/refresh",
    response_model=TokenPairResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponse,
            "description": "Invalid or expired refresh token.",
        },
        status.HTTP_403_FORBIDDEN: {
            "model": ErrorResponse,
            "description": "User account is inactive.",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "Authentication service is temporarily unavailable.",
        },
    },
)
def refresh(
    request: RefreshRequest,
    session: Annotated[Session, Depends(get_db)],
    session_repository: Annotated[
        SessionRepository,
        Depends(get_session_repository),
    ],
) -> TokenPairResponse:
    return AuthService(session).refresh(request, session_repository)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponse,
            "description": "Invalid or expired refresh token.",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "Authentication service is temporarily unavailable.",
        },
    },
)
def logout(
    request: LogoutRequest,
    session: Annotated[Session, Depends(get_db)],
    session_repository: Annotated[
        SessionRepository,
        Depends(get_session_repository),
    ],
) -> None:
    AuthService(session).logout(request, session_repository)
