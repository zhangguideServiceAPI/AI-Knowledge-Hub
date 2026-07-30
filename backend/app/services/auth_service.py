from time import time

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    EmailAlreadyRegisteredError,
    InactiveUserError,
    InvalidAccessTokenError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    LoginRateLimitExceededError,
)
from app.core.logging import logger
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    calculate_initial_session_expiration,
    calculate_rotated_session_expiration,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    generate_session_id,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.db.repositories.session_repository import (
    SessionDeletion,
    SessionDeletionResult,
    SessionRecord,
    SessionRepository,
    SessionRotation,
    SessionRotationResult,
)
from app.db.repositories.user_repository import UserRepository
from app.models.user import User, UserStatus
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPairResponse,
)
from app.schemas.user import UserResponse
from app.services.login_rate_limiter import LoginRateLimiter


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

        logger.info(
            "auth.register.success user_id=%s",
            response.id,
        )
        return response

    def login(
        self,
        request: LoginRequest,
        rate_limiter: LoginRateLimiter,
        session_repository: SessionRepository,
    ) -> TokenPairResponse:
        email = str(request.email).strip().lower()

        if not rate_limiter.reserve_attempt(email):
            logger.warning("auth.login.rate_limited reason=attempt_limit_exceeded")
            raise LoginRateLimitExceededError()

        user_model = self._user_repository.get_by_email(email)
        # 这是为了防止攻击者通过响应时间判断邮箱是否已经注册，也叫用户枚举攻击。
        if user_model is None:
            verify_password(request.password, DUMMY_PASSWORD_HASH)
            raise InvalidCredentialsError()

        if not verify_password(request.password, user_model.password_hash):
            raise InvalidCredentialsError()

        if user_model.status != UserStatus.ACTIVE:
            raise InactiveUserError()

        rate_limiter.reset(email)

        created_at = int(time())
        session_expiration = calculate_initial_session_expiration(created_at)
        ttl_seconds = session_expiration.expires_at - created_at

        session_id = generate_session_id()
        refresh_token = create_refresh_token(
            user_id=user_model.id,
            session_id=session_id,
            expires_at=session_expiration.expires_at,
        )
        access_token = create_access_token(
            user_model.id,
            session_expires_at=session_expiration.expires_at,
        )

        session_repository.create(
            SessionRecord(
                session_id=session_id,
                user_id=user_model.id,
                refresh_token_hash=hash_refresh_token(refresh_token),
                created_at=created_at,
                last_used_at=created_at,
                expires_at=session_expiration.expires_at,
                absolute_expires_at=session_expiration.absolute_expires_at,
            ),
            ttl_seconds=ttl_seconds,
        )

        logger.info(
            "auth.login.success user_id=%s",
            user_model.id,
        )

        return TokenPairResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=min(
                settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                ttl_seconds,
            ),
            refresh_expires_in=ttl_seconds,
        )

    def get_current_user(self, token: str) -> UserResponse:
        user_id = decode_access_token(token)
        user_model = self._user_repository.get_by_id(user_id)

        if user_model is None:
            raise InvalidAccessTokenError()

        if user_model.status != UserStatus.ACTIVE:
            raise InactiveUserError()

        return UserResponse.model_validate(user_model)

    def refresh(
        self,
        request: RefreshRequest,
        session_repository: SessionRepository,
    ) -> TokenPairResponse:
        claims = decode_refresh_token(request.refresh_token)
        session_record = session_repository.get(claims.session_id)

        if session_record is None:
            logger.warning(
                "auth.refresh.rejected user_id=%s reason=session_not_found",
                claims.user_id,
            )
            raise InvalidRefreshTokenError()

        if session_record.user_id != claims.user_id:
            logger.warning(
                "auth.refresh.rejected user_id=%s reason=user_mismatch",
                claims.user_id,
            )
            raise InvalidRefreshTokenError()

        user_model = self._user_repository.get_by_id(claims.user_id)

        if user_model is None:
            logger.warning(
                "auth.refresh.rejected user_id=%s reason=user_not_found",
                claims.user_id,
            )
            raise InvalidRefreshTokenError()

        if user_model.status != UserStatus.ACTIVE:
            raise InactiveUserError()

        rotated_at = int(time())
        rotated_expires_at = calculate_rotated_session_expiration(
            rotated_at=rotated_at,
            current_expires_at=session_record.expires_at,
            absolute_expires_at=session_record.absolute_expires_at,
        )
        ttl_seconds = rotated_expires_at - rotated_at
        if ttl_seconds <= 0:
            logger.warning(
                "auth.refresh.rejected user_id=%s reason=session_expired",
                user_model.id,
            )
            raise InvalidRefreshTokenError()

        new_refresh_token = create_refresh_token(
            user_id=user_model.id,
            session_id=claims.session_id,
            expires_at=rotated_expires_at,
        )
        new_access_token = create_access_token(
            user_model.id,
            session_expires_at=rotated_expires_at,
        )

        result = session_repository.rotate(
            SessionRotation(
                session_id=claims.session_id,
                user_id=user_model.id,
                expected_refresh_token_hash=hash_refresh_token(request.refresh_token),
                new_refresh_token_hash=hash_refresh_token(new_refresh_token),
                rotated_at=rotated_at,
                expires_at=rotated_expires_at,
                ttl_seconds=ttl_seconds,
            )
        )

        if result != SessionRotationResult.SUCCESS:
            if result is SessionRotationResult.TOKEN_MISMATCH:
                logger.warning(
                    "auth.refresh.replay_detected user_id=%s reason=token_mismatch",
                    user_model.id,
                )
            else:
                logger.warning(
                    "auth.refresh.rejected user_id=%s reason=session_not_found",
                    user_model.id,
                )
            raise InvalidRefreshTokenError()

        logger.info(
            "auth.refresh.success user_id=%s",
            user_model.id,
        )

        return TokenPairResponse(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            expires_in=min(
                settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                ttl_seconds,
            ),
            refresh_expires_in=ttl_seconds,
        )

    def logout(
        self,
        request: LogoutRequest,
        session_repository: SessionRepository,
    ) -> None:
        claims = decode_refresh_token(request.refresh_token)

        result = session_repository.delete_if_matches(
            SessionDeletion(
                session_id=claims.session_id,
                user_id=claims.user_id,
                expected_refresh_token_hash=hash_refresh_token(request.refresh_token),
            )
        )
        if result is SessionDeletionResult.SESSION_MISMATCH:
            raise InvalidRefreshTokenError()

        logout_result = (
            "deleted" if result is SessionDeletionResult.SUCCESS else "already_missing"
        )
        logger.info(
            "auth.logout.success user_id=%s result=%s",
            claims.user_id,
            logout_result,
        )
