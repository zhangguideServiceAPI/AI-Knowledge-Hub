from datetime import datetime, timedelta, timezone

import pytest
from jose import JWTError, jwt

from app.core.config import settings
from app.core.exceptions import InvalidAccessTokenError
from app.core.security import (
    BCRYPT_PASSWORD_MAX_BYTES,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_password_does_not_return_plaintext() -> None:
    password = "mysecretpassword"
    password_hash = hash_password(password)

    assert password_hash != password


def test_verify_password() -> None:
    password = "mysecretpassword"
    password_hash = hash_password(password)

    assert verify_password(password, password_hash) is True
    assert verify_password("wrong-password", password_hash) is False


def test_hash_password_uses_random_salt() -> None:
    password = "mysecretpassword"
    password_hash1 = hash_password(password)
    password_hash2 = hash_password(password)

    assert password_hash1 != password_hash2
    assert verify_password(password, password_hash1) is True
    assert verify_password(password, password_hash2) is True


def test_hash_password_enforces_bcrypt_byte_limit() -> None:
    maximum_password = "a" * BCRYPT_PASSWORD_MAX_BYTES
    too_long_password = "a" * (BCRYPT_PASSWORD_MAX_BYTES + 1)

    password_hash = hash_password(maximum_password)

    assert verify_password(maximum_password, password_hash) is True

    with pytest.raises(ValueError, match="72 UTF-8 bytes"):
        hash_password(too_long_password)


def test_verify_password_rejects_password_over_bcrypt_limit() -> None:
    password_hash = hash_password("correct-password")
    too_long_password = "a" * (BCRYPT_PASSWORD_MAX_BYTES + 1)

    assert verify_password(too_long_password, password_hash) is False


def test_create_access_token_contains_expected_claims() -> None:
    user_id = 123

    token = create_access_token(user_id)
    payload = jwt.decode(
        token,
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithms=[settings.JWT_ALGORITHM],
    )

    assert payload["sub"] == str(user_id)
    assert payload["type"] == "access"
    assert payload["exp"] - payload["iat"] == (
        settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


def test_access_token_rejects_wrong_secret() -> None:
    token = create_access_token(123)

    with pytest.raises(JWTError):
        jwt.decode(
            token,
            "wrong-secret",
            algorithms=[settings.JWT_ALGORITHM],
        )


def test_decode_access_token_returns_user_id() -> None:
    token = create_access_token(123)

    user_id = decode_access_token(token)

    assert user_id == 123


def test_decode_access_token_rejects_wrong_signature() -> None:
    token = jwt.encode(
        {
            "sub": "123",
            "type": "access",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
        },
        "wrong-secret",
        algorithm=settings.JWT_ALGORITHM,
    )

    with pytest.raises(InvalidAccessTokenError) as error:
        decode_access_token(token)

    assert isinstance(error.value.__cause__, JWTError)


def test_decode_access_token_rejects_expired_token() -> None:
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": "123",
            "type": "access",
            "iat": now - timedelta(minutes=2),
            "exp": now - timedelta(minutes=1),
        },
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithm=settings.JWT_ALGORITHM,
    )

    with pytest.raises(InvalidAccessTokenError) as error:
        decode_access_token(token)

    assert isinstance(error.value.__cause__, JWTError)


def test_decode_access_token_rejects_wrong_token_type() -> None:
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": "123",
            "type": "refresh",
            "iat": now,
            "exp": now + timedelta(days=7),
        },
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithm=settings.JWT_ALGORITHM,
    )

    with pytest.raises(InvalidAccessTokenError) as error:
        decode_access_token(token)

    assert error.value.__cause__ is None


@pytest.mark.parametrize("missing_claim", ["sub", "iat", "exp"])
def test_decode_access_token_requires_standard_claims(
    missing_claim: str,
) -> None:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "123",
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=30),
    }
    payload.pop(missing_claim)
    token = jwt.encode(
        payload,
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithm=settings.JWT_ALGORITHM,
    )

    with pytest.raises(InvalidAccessTokenError) as error:
        decode_access_token(token)

    assert isinstance(error.value.__cause__, JWTError)


def test_decode_access_token_rejects_non_positive_user_id() -> None:
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": "0",
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=30),
        },
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithm=settings.JWT_ALGORITHM,
    )

    with pytest.raises(InvalidAccessTokenError) as error:
        decode_access_token(token)

    assert error.value.__cause__ is None
