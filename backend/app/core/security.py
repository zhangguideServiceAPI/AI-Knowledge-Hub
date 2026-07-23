from datetime import datetime, timedelta, timezone

import bcrypt

from jose import JWTError, jwt

from app.core.config import settings
from app.core.exceptions import InvalidAccessTokenError

BCRYPT_PASSWORD_MAX_BYTES = 72
ACCESS_TOKEN_TYPE = "access"
DUMMY_PASSWORD_HASH = "$2b$12$j9ZSWTtfl01rAX.gKvsR5Oye7O1/5uLlq3qS8Nrfp98wFje4yaehq"


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


def create_access_token(user_id: int) -> str:
    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(
        minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
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
