from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from secrets import token_urlsafe

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings
from app.core.exceptions import (
    InvalidAccessTokenError,
    InvalidRefreshTokenError,
)

BCRYPT_PASSWORD_MAX_BYTES = 72
ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"
DUMMY_PASSWORD_HASH = "$2b$12$j9ZSWTtfl01rAX.gKvsR5Oye7O1/5uLlq3qS8Nrfp98wFje4yaehq"

AUTH_RANDOM_BYTES = 32
# 一天的秒数
SECONDS_PER_DAY = 86_400


def _encode_password(password: str) -> bytes:
    password_bytes = password.encode("utf-8")

    if len(password_bytes) > BCRYPT_PASSWORD_MAX_BYTES:
        raise ValueError("Password cannot exceed 72 UTF-8 bytes.")

    return password_bytes


def hash_password(password: str) -> str:
    password_bytes = _encode_password(password)
    password_hash = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
    return password_hash.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        password_bytes = _encode_password(password)
    except ValueError:
        return False

    return bcrypt.checkpw(
        password_bytes,
        password_hash.encode("utf-8"),
    )


def create_access_token(
    user_id: int,
    session_expires_at: int | None = None,
) -> str:
    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(
        minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
    )

    if session_expires_at is not None:
        expires_at = min(
            expires_at,
            datetime.fromtimestamp(session_expires_at, tz=timezone.utc),
        )

    payload = {
        "sub": str(user_id),
        "type": ACCESS_TOKEN_TYPE,
        "iat": issued_at,
        "exp": expires_at,
    }

    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> int:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY.get_secret_value(),
            algorithms=[settings.JWT_ALGORITHM],
            options={
                "require_sub": True,
                "require_iat": True,
                "require_exp": True,
            },
        )

        if payload.get("type") != ACCESS_TOKEN_TYPE:
            raise InvalidAccessTokenError()

        user_id = int(payload["sub"])

        if user_id <= 0:
            raise InvalidAccessTokenError()

    except (JWTError, KeyError, TypeError, ValueError) as error:
        raise InvalidAccessTokenError() from error

    return user_id


def hash_refresh_token(token: str) -> str:
    token_bytes = token.encode("utf-8")
    return sha256(token_bytes).hexdigest()


def generate_session_id() -> str:
    return token_urlsafe(AUTH_RANDOM_BYTES)


@dataclass(frozen=True)
class SessionExpiration:
    expires_at: int
    absolute_expires_at: int


@dataclass(frozen=True)
class RefreshTokenClaims:
    """Refresh JWT 验证通过后交给 Service 使用的字段。"""

    user_id: int
    session_id: str
    token_id: str
    issued_at: int
    expires_at: int


def calculate_initial_session_expiration(
    created_at: int,
) -> SessionExpiration:
    """根据 Session 首次创建时的 Unix 秒时间戳计算过期边界。"""
    expires_at = created_at + settings.SESSION_TTL_DAYS * SECONDS_PER_DAY

    # Sliding 模式保留独立的绝对上限，避免活跃会话无限续期。
    if settings.SESSION_EXPIRATION_MODE == "sliding":
        absolute_expires_at = (
            created_at + settings.SESSION_ABSOLUTE_MAX_DAYS * SECONDS_PER_DAY
        )
    else:
        # Absolute 模式的首次到期时间就是最终上限。
        absolute_expires_at = expires_at

    return SessionExpiration(
        expires_at=expires_at,
        absolute_expires_at=absolute_expires_at,
    )


def calculate_rotated_session_expiration(
    rotated_at: int,
    current_expires_at: int,
    absolute_expires_at: int,
) -> int:
    """计算一次成功 Rotation 后 Session 的当前过期时间。

    Args:
        rotated_at: 新 Refresh Token 的签发时间，Unix 秒。
        current_expires_at: Redis Session 当前的过期时间。
        absolute_expires_at: Session 永远不能超过的最终过期时间。
    """
    if settings.SESSION_EXPIRATION_MODE == "absolute":
        return current_expires_at

    sliding_expires_at = rotated_at + settings.SESSION_TTL_DAYS * SECONDS_PER_DAY

    # 即使持续活跃，Sliding Session 也不能超过登录时固定的绝对上限。
    return min(sliding_expires_at, absolute_expires_at)


def create_refresh_token(
    user_id: int,
    session_id: str,
    expires_at: int,
) -> str:
    """签发绑定到指定 Session 的 Refresh JWT。

    Args:
        user_id: 本地用户 ID，对应 JWT 的 sub。
        session_id: 当前设备的 Session ID，对应 JWT 的 sid。
        expires_at: 当前 Session 的过期时间，Unix 秒，对应 JWT 的 exp。
    """
    issued_at = datetime.now(timezone.utc)

    payload = {
        "sub": str(user_id),
        "type": REFRESH_TOKEN_TYPE,
        "sid": session_id,
        # sid 在同一 Session 内不变，但每次 Rotation 都必须生成新的 jti。
        "jti": token_urlsafe(AUTH_RANDOM_BYTES),
        "iat": issued_at,
        "exp": expires_at,
    }

    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_refresh_token(token: str) -> RefreshTokenClaims:
    """验证 Refresh JWT 并返回业务字段，不检查 Redis Session。

    Args:
        token: 客户端提交的原始 Refresh JWT。
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY.get_secret_value(),
            algorithms=[settings.JWT_ALGORITHM],
            options={
                "require_sub": True,
                "require_iat": True,
                "require_exp": True,
            },
        )

        if payload.get("type") != REFRESH_TOKEN_TYPE:
            raise InvalidRefreshTokenError()

        # sid 和 jti 是必填业务 Claim，使用 [] 可以让缺失字段进入异常分支。
        session_id = payload["sid"]
        token_id = payload["jti"]

        if (
            not isinstance(session_id, str)
            or not session_id
            or not isinstance(token_id, str)
            or not token_id
        ):
            raise InvalidRefreshTokenError()

        user_id = int(payload["sub"])
        issued_at = int(payload["iat"])
        expires_at = int(payload["exp"])

        if user_id <= 0:
            raise InvalidRefreshTokenError()

    except (JWTError, KeyError, TypeError, ValueError) as error:
        raise InvalidRefreshTokenError() from error

    return RefreshTokenClaims(
        user_id=user_id,
        session_id=session_id,
        token_id=token_id,
        issued_at=issued_at,
        expires_at=expires_at,
    )
