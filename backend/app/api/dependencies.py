from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.exceptions import InvalidAccessTokenError
from app.db.session import get_db
from app.schemas.user import UserResponse
from app.services.auth_service import AuthService


bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> UserResponse:
    if credentials is None:
        raise InvalidAccessTokenError()

    return AuthService(session).get_current_user(
        credentials.credentials,
    )
