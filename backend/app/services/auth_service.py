from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    EmailAlreadyRegisteredError,
    InactiveUserError,
    InvalidAccessTokenError,
    InvalidCredentialsError,
)
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.db.repositories.user_repository import UserRepository
from app.models.user import User, UserStatus
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.schemas.user import UserResponse


class AuthService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._user_repository = UserRepository(session)

    def register(self, request: RegisterRequest) -> UserResponse:
        email = str(request.email).strip().lower()
        nickname = request.nickname.strip() if request.nickname else None
        nickname = nickname or None
        password_hash = hash_password(request.password)

        try:
            with self._session.begin():
                existing_user = self._user_repository.get_by_email(email)

                if existing_user is not None:
                    raise EmailAlreadyRegisteredError()

                user_model = User(
                    email=email,
                    password_hash=password_hash,
                    nickname=nickname,
                )
                created_user_model = self._user_repository.create(user_model)
                response = UserResponse.model_validate(created_user_model)

        except IntegrityError as error:
            raise EmailAlreadyRegisteredError() from error

        return response

    def login(self, request: LoginRequest) -> TokenResponse:
        email = str(request.email).strip().lower()
        user_model = self._user_repository.get_by_email(email)

        if user_model is None:
            verify_password(request.password, DUMMY_PASSWORD_HASH)
            raise InvalidCredentialsError()

        if not verify_password(request.password, user_model.password_hash):
            raise InvalidCredentialsError()

        if user_model.status != UserStatus.ACTIVE:
            raise InactiveUserError()

        access_token = create_access_token(user_model.id)

        return TokenResponse(
            access_token=access_token,
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    def get_current_user(self, token: str) -> UserResponse:
        user_id = decode_access_token(token)
        user_model = self._user_repository.get_by_id(user_id)

        if user_model is None:
            raise InvalidAccessTokenError()

        if user_model.status != UserStatus.ACTIVE:
            raise InactiveUserError()

        return UserResponse.model_validate(user_model)
