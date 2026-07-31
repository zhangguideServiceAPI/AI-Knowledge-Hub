from datetime import datetime, timedelta, timezone

import pytest
from jose import JWTError, jwt
from pydantic import SecretStr

from app.core.config import settings
from app.core.exceptions import (
    InvalidAccessTokenError,
    InvalidRefreshTokenError,
)
from app.core.security import (
    AccessTokenClaims,
    BCRYPT_PASSWORD_MAX_BYTES,
    SessionExpiration,
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
    session_id = "session-abc"

    token = create_access_token(user_id, session_id)
    payload = jwt.decode(
        token,
        settings.JWT_SIGNING_KEYS[settings.JWT_ACTIVE_KEY_ID].get_secret_value(),
        algorithms=[settings.JWT_ALGORITHM],
    )

    assert payload["sub"] == str(user_id)
    assert payload["type"] == "access"
    assert payload["sid"] == session_id
    assert payload["exp"] - payload["iat"] == (
        settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


# Session 剩余 10 分钟
#   -> Access 只有 10 分钟
def test_create_access_token_does_not_outlive_session() -> None:
    session_expires_at = int(datetime.now(timezone.utc).timestamp()) + 600

    token = create_access_token(
        user_id=123,
        session_id="session-abc",
        session_expires_at=session_expires_at,
    )
    payload = jwt.decode(
        token,
        settings.JWT_SIGNING_KEYS[settings.JWT_ACTIVE_KEY_ID].get_secret_value(),
        algorithms=[settings.JWT_ALGORITHM],
    )

    assert payload["exp"] == session_expires_at
    assert payload["exp"] - payload["iat"] <= 600


# Session 剩余 7 天
#   -> Access 仍只有 30 分钟
def test_create_access_token_does_not_extend_default_lifetime() -> None:
    session_expires_at = int(
        (datetime.now(timezone.utc) + timedelta(days=7)).timestamp()
    )

    token = create_access_token(
        user_id=123,
        session_id="session-abc",
        session_expires_at=session_expires_at,
    )
    payload = jwt.decode(
        token,
        settings.JWT_SIGNING_KEYS[settings.JWT_ACTIVE_KEY_ID].get_secret_value(),
        algorithms=[settings.JWT_ALGORITHM],
    )

    assert payload["exp"] - payload["iat"] == (
        settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )
    assert payload["exp"] < session_expires_at


def test_access_token_rejects_wrong_secret() -> None:
    token = create_access_token(123, "session-abc")

    with pytest.raises(JWTError):
        jwt.decode(
            token,
            "wrong-secret",
            algorithms=[settings.JWT_ALGORITHM],
        )


def test_decode_access_token_returns_claims() -> None:
    token = create_access_token(123, "session-abc")

    claims = decode_access_token(token)

    assert isinstance(claims, AccessTokenClaims)
    assert claims.user_id == 123
    assert claims.session_id == "session-abc"
    assert isinstance(claims.issued_at, int)
    assert isinstance(claims.expires_at, int)


def test_decode_access_token_accepts_legacy_token_without_session_id() -> None:
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": "123",
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=30),
        },
        settings.JWT_SIGNING_KEYS[settings.JWT_ACTIVE_KEY_ID].get_secret_value(),
        algorithm=settings.JWT_ALGORITHM,
        headers={"kid": settings.JWT_ACTIVE_KEY_ID},
    )

    claims = decode_access_token(token)

    assert claims.user_id == 123
    assert claims.session_id is None


@pytest.mark.parametrize("session_id", ["", 42])
def test_decode_access_token_rejects_invalid_session_id(
    session_id: object,
) -> None:
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": "123",
            "type": "access",
            "sid": session_id,
            "iat": now,
            "exp": now + timedelta(minutes=30),
        },
        settings.JWT_SIGNING_KEYS[settings.JWT_ACTIVE_KEY_ID].get_secret_value(),
        algorithm=settings.JWT_ALGORITHM,
        headers={"kid": settings.JWT_ACTIVE_KEY_ID},
    )

    with pytest.raises(InvalidAccessTokenError) as error:
        decode_access_token(token)

    assert error.value.__cause__ is None


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
        headers={"kid": settings.JWT_ACTIVE_KEY_ID},
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
        settings.JWT_SIGNING_KEYS[settings.JWT_ACTIVE_KEY_ID].get_secret_value(),
        algorithm=settings.JWT_ALGORITHM,
        headers={"kid": settings.JWT_ACTIVE_KEY_ID},
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
        settings.JWT_SIGNING_KEYS[settings.JWT_ACTIVE_KEY_ID].get_secret_value(),
        algorithm=settings.JWT_ALGORITHM,
        headers={"kid": settings.JWT_ACTIVE_KEY_ID},
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
        settings.JWT_SIGNING_KEYS[settings.JWT_ACTIVE_KEY_ID].get_secret_value(),
        algorithm=settings.JWT_ALGORITHM,
        headers={"kid": settings.JWT_ACTIVE_KEY_ID},
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
        settings.JWT_SIGNING_KEYS[settings.JWT_ACTIVE_KEY_ID].get_secret_value(),
        algorithm=settings.JWT_ALGORITHM,
        headers={"kid": settings.JWT_ACTIVE_KEY_ID},
    )

    with pytest.raises(InvalidAccessTokenError) as error:
        decode_access_token(token)

    assert error.value.__cause__ is None


def test_create_access_token_uses_active_signing_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_secret = "first-test-signing-key-at-least-32-characters"
    second_secret = "second-test-signing-key-at-least-32-characters"

    monkeypatch.setattr(settings, "JWT_ACTIVE_KEY_ID", "v2")
    monkeypatch.setattr(
        settings,
        "JWT_SIGNING_KEYS",
        {
            "v1": SecretStr(first_secret),
            "v2": SecretStr(second_secret),
        },
    )

    token = create_access_token(user_id=123, session_id="session-abc")

    header = jwt.get_unverified_header(token)
    payload = jwt.decode(
        token,
        second_secret,
        algorithms=[settings.JWT_ALGORITHM],
    )

    assert header["kid"] == "v2"
    assert payload["sub"] == "123"

    with pytest.raises(JWTError):
        jwt.decode(
            token,
            first_secret,
            algorithms=[settings.JWT_ALGORITHM],
        )


def test_decode_access_token_accepts_previous_signing_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_secret = "first-test-signing-key-at-least-32-characters"
    second_secret = "second-test-signing-key-at-least-32-characters"

    monkeypatch.setattr(
        settings,
        "JWT_SIGNING_KEYS",
        {
            "v1": SecretStr(first_secret),
            "v2": SecretStr(second_secret),
        },
    )
    monkeypatch.setattr(settings, "JWT_ACTIVE_KEY_ID", "v1")
    old_token = create_access_token(user_id=123, session_id="session-abc")

    # 模拟正常轮换：新 Token 改用 v2，但 v1 仍留在 Key Ring。
    monkeypatch.setattr(settings, "JWT_ACTIVE_KEY_ID", "v2")
    claims = decode_access_token(old_token)

    assert claims.user_id == 123
    assert claims.session_id == "session-abc"


def test_decode_access_token_rejects_missing_key_id() -> None:
    now = datetime.now(timezone.utc)
    active_secret = settings.JWT_SIGNING_KEYS[
        settings.JWT_ACTIVE_KEY_ID
    ].get_secret_value()

    token = jwt.encode(
        {
            "sub": "123",
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=30),
        },
        active_secret,
        algorithm=settings.JWT_ALGORITHM,
    )

    with pytest.raises(InvalidAccessTokenError) as error:
        decode_access_token(token)

    assert isinstance(error.value.__cause__, JWTError)


def test_decode_refresh_token_rejects_unknown_key_id() -> None:
    now = datetime.now(timezone.utc)

    token = jwt.encode(
        {
            "sub": "42",
            "type": "refresh",
            "sid": "session-abc",
            "jti": "token-abc",
            "iat": now,
            "exp": now + timedelta(days=7),
        },
        "unknown-test-secret-at-least-32-characters",
        algorithm=settings.JWT_ALGORITHM,
        headers={"kid": "unknown-key"},
    )

    with pytest.raises(InvalidRefreshTokenError) as error:
        decode_refresh_token(token)

    assert isinstance(error.value.__cause__, JWTError)


def test_hash_refresh_token_returns_sha256_digest() -> None:
    token = "refresh-token"

    token_hash = hash_refresh_token(token)

    assert token_hash == (
        "0eb17643d4e9261163783a420859c92c7d212fa9624106a12b510afbec266120"
    )
    assert token_hash != token


def test_generate_session_id_returns_unique_random_values() -> None:
    first_session_id = generate_session_id()
    second_session_id = generate_session_id()

    assert isinstance(first_session_id, str)
    assert len(first_session_id) >= 32
    assert first_session_id != second_session_id


def test_calculate_initial_session_expiration_in_absolute_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 临时切换全局 Settings，测试结束后 pytest 会自动恢复。
    monkeypatch.setattr(settings, "SESSION_EXPIRATION_MODE", "absolute")
    monkeypatch.setattr(settings, "SESSION_TTL_DAYS", 7)

    expiration = calculate_initial_session_expiration(created_at=1_000)

    assert expiration == SessionExpiration(
        expires_at=605_800, absolute_expires_at=605_800
    )


def test_calculate_initial_session_expiration_in_sliding_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "SESSION_EXPIRATION_MODE", "sliding")
    monkeypatch.setattr(settings, "SESSION_TTL_DAYS", 7)
    monkeypatch.setattr(settings, "SESSION_ABSOLUTE_MAX_DAYS", 30)

    expiration = calculate_initial_session_expiration(created_at=1_000)

    assert expiration == SessionExpiration(
        expires_at=605_800,
        absolute_expires_at=2_593_000,
    )


def test_rotated_session_expiration_stays_fixed_in_absolute_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "SESSION_EXPIRATION_MODE", "absolute")

    expires_at = calculate_rotated_session_expiration(
        rotated_at=500_000,
        current_expires_at=605_800,
        absolute_expires_at=605_800,
    )

    assert expires_at == 605_800


def test_rotated_session_expiration_extends_in_sliding_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "SESSION_EXPIRATION_MODE", "sliding")
    monkeypatch.setattr(settings, "SESSION_TTL_DAYS", 7)

    expires_at = calculate_rotated_session_expiration(
        rotated_at=500_000,
        current_expires_at=605_800,
        absolute_expires_at=2_593_000,
    )

    assert expires_at == 1_104_800


def test_rotated_session_expiration_stops_at_absolute_max(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "SESSION_EXPIRATION_MODE", "sliding")
    monkeypatch.setattr(settings, "SESSION_TTL_DAYS", 7)

    expires_at = calculate_rotated_session_expiration(
        rotated_at=2_500_000,
        current_expires_at=2_500_000,
        absolute_expires_at=2_593_000,
    )

    assert expires_at == 2_593_000


def test_create_refresh_token_contains_expected_claims() -> None:
    expires_at = int((datetime.now(timezone.utc) + timedelta(days=7)).timestamp())

    token = create_refresh_token(
        user_id=42,
        session_id="session-abc",
        expires_at=expires_at,
    )
    payload = jwt.decode(
        token,
        settings.JWT_SIGNING_KEYS[settings.JWT_ACTIVE_KEY_ID].get_secret_value(),
        algorithms=[settings.JWT_ALGORITHM],
    )

    assert payload["sub"] == "42"
    assert payload["type"] == "refresh"
    assert payload["sid"] == "session-abc"
    assert isinstance(payload["jti"], str)
    assert len(payload["jti"]) >= 32
    assert isinstance(payload["iat"], int)
    assert payload["exp"] == expires_at


# 再验证同一 Session 每次 Rotation 的 jti 不同：
def test_create_refresh_token_rotates_jti_for_same_session() -> None:
    expires_at = int((datetime.now(timezone.utc) + timedelta(days=7)).timestamp())

    first_token = create_refresh_token(42, "session-abc", expires_at)
    second_token = create_refresh_token(42, "session-abc", expires_at)

    first_payload = jwt.decode(
        first_token,
        settings.JWT_SIGNING_KEYS[settings.JWT_ACTIVE_KEY_ID].get_secret_value(),
        algorithms=[settings.JWT_ALGORITHM],
    )
    second_payload = jwt.decode(
        second_token,
        settings.JWT_SIGNING_KEYS[settings.JWT_ACTIVE_KEY_ID].get_secret_value(),
        algorithms=[settings.JWT_ALGORITHM],
    )

    assert first_payload["sid"] == second_payload["sid"]
    assert first_payload["jti"] != second_payload["jti"]
    assert first_token != second_token


def test_decode_refresh_token_returns_claims() -> None:
    expires_at = int((datetime.now(timezone.utc) + timedelta(days=7)).timestamp())
    token = create_refresh_token(42, "session-abc", expires_at)

    claims = decode_refresh_token(token)

    assert claims.user_id == 42
    assert claims.session_id == "session-abc"
    assert len(claims.token_id) >= 32
    assert isinstance(claims.issued_at, int)
    assert claims.expires_at == expires_at


def test_decode_refresh_token_rejects_access_token() -> None:
    token = create_access_token(42, "session-abc")

    with pytest.raises(InvalidRefreshTokenError) as error:
        decode_refresh_token(token)

    assert error.value.__cause__ is None


@pytest.mark.parametrize(
    "missing_claim",
    ["sub", "sid", "jti", "iat", "exp"],
)
def test_decode_refresh_token_requires_claims(missing_claim: str) -> None:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "42",
        "type": "refresh",
        "sid": "session-abc",
        "jti": "token-abc",
        "iat": now,
        "exp": now + timedelta(days=7),
    }
    payload.pop(missing_claim)
    token = jwt.encode(
        payload,
        settings.JWT_SIGNING_KEYS[settings.JWT_ACTIVE_KEY_ID].get_secret_value(),
        algorithm=settings.JWT_ALGORITHM,
        headers={"kid": settings.JWT_ACTIVE_KEY_ID},
    )

    with pytest.raises(InvalidRefreshTokenError):
        decode_refresh_token(token)


def test_decode_refresh_token_rejects_expired_token() -> None:
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": "42",
            "type": "refresh",
            "sid": "session-abc",
            "jti": "token-abc",
            "iat": now - timedelta(minutes=2),
            "exp": now - timedelta(minutes=1),
        },
        settings.JWT_SIGNING_KEYS[settings.JWT_ACTIVE_KEY_ID].get_secret_value(),
        algorithm=settings.JWT_ALGORITHM,
        headers={"kid": settings.JWT_ACTIVE_KEY_ID},
    )

    with pytest.raises(InvalidRefreshTokenError) as error:
        decode_refresh_token(token)

    assert isinstance(error.value.__cause__, JWTError)


def test_create_refresh_token_uses_active_signing_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_secret = "first-test-signing-key-at-least-32-characters"
    second_secret = "second-test-signing-key-at-least-32-characters"

    monkeypatch.setattr(settings, "JWT_ACTIVE_KEY_ID", "v2")
    monkeypatch.setattr(
        settings,
        "JWT_SIGNING_KEYS",
        {
            "v1": SecretStr(first_secret),
            "v2": SecretStr(second_secret),
        },
    )

    expires_at = int((datetime.now(timezone.utc) + timedelta(days=7)).timestamp())
    token = create_refresh_token(
        user_id=42,
        session_id="session-abc",
        expires_at=expires_at,
    )

    header = jwt.get_unverified_header(token)
    payload = jwt.decode(
        token,
        second_secret,
        algorithms=[settings.JWT_ALGORITHM],
    )

    assert header["kid"] == "v2"
    assert payload["type"] == "refresh"
    assert payload["sid"] == "session-abc"

    with pytest.raises(JWTError):
        jwt.decode(
            token,
            first_secret,
            algorithms=[settings.JWT_ALGORITHM],
        )


def test_decode_refresh_token_accepts_previous_signing_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_secret = "first-test-signing-key-at-least-32-characters"
    second_secret = "second-test-signing-key-at-least-32-characters"

    monkeypatch.setattr(
        settings,
        "JWT_SIGNING_KEYS",
        {
            "v1": SecretStr(first_secret),
            "v2": SecretStr(second_secret),
        },
    )
    monkeypatch.setattr(settings, "JWT_ACTIVE_KEY_ID", "v1")

    expires_at = int((datetime.now(timezone.utc) + timedelta(days=7)).timestamp())
    old_token = create_refresh_token(
        user_id=42,
        session_id="session-abc",
        expires_at=expires_at,
    )

    # 新 Token 已切换到 v2，但旧 v1 仍留在验证 Key Ring。
    monkeypatch.setattr(settings, "JWT_ACTIVE_KEY_ID", "v2")

    claims = decode_refresh_token(old_token)

    assert claims.user_id == 42
    assert claims.session_id == "session-abc"
    assert claims.expires_at == expires_at
