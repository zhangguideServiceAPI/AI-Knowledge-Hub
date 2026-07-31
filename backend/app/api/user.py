from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_access_token,
    get_current_user,
    get_session_repository,
)
from app.db.repositories.session_repository import SessionRepository
from app.db.session import get_db
from app.schemas.error import ErrorResponse
from app.schemas.session import UserSessionListResponse
from app.schemas.user import UserResponse
from app.services.auth_service import AuthService


router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponse,
            "description": "Invalid or missing access token.",
        },
        status.HTTP_403_FORBIDDEN: {
            "model": ErrorResponse,
            "description": "User account is inactive.",
        },
    },
)
def get_me(
    current_user: Annotated[
        UserResponse,
        Depends(get_current_user),
    ],
) -> UserResponse:
    return current_user


@router.get(
    "/sessions",
    status_code=status.HTTP_200_OK,
    response_model=UserSessionListResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponse,
            "description": "Invalid or missing access token.",
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
def list_sessions(
    token: Annotated[str, Depends(get_access_token)],
    session: Annotated[Session, Depends(get_db)],
    session_repository: Annotated[SessionRepository, Depends(get_session_repository)],
) -> UserSessionListResponse:
    return AuthService(session).list_sessions(
        token,
        session_repository,
    )


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponse,
            "description": "Invalid or missing access token.",
        },
        status.HTTP_403_FORBIDDEN: {
            "model": ErrorResponse,
            "description": "User account is inactive.",
        },
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Session not found.",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "Authentication service is temporarily unavailable.",
        },
    },
)
def revoke_session(
    session_id: str,
    token: Annotated[str, Depends(get_access_token)],
    session: Annotated[Session, Depends(get_db)],
    session_repository: Annotated[SessionRepository, Depends(get_session_repository)],
) -> None:
    AuthService(session).revoke_session(
        token,
        target_session_id=session_id,
        session_repository=session_repository,
    )


@router.delete(
    "/sessions",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponse,
            "description": "Invalid or missing access token.",
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
def revoke_all_sessions(
    token: Annotated[str, Depends(get_access_token)],
    session: Annotated[Session, Depends(get_db)],
    session_repository: Annotated[SessionRepository, Depends(get_session_repository)],
) -> None:
    AuthService(session).revoke_all_sessions(
        token,
        session_repository,
    )
