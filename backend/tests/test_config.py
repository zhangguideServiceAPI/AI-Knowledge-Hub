import pytest
from pydantic import ValidationError

from app.core.config import Settings

VALID_JWT_SECRET = "test-only-jwt-secret-key-32-characters"
VALID_REDIS_PASSWORD = "test-only-redis-password"


def test_settings_rejects_short_jwt_secret() -> None:
    with pytest.raises(ValidationError) as error:
        Settings(
            _env_file=None,
            JWT_SECRET_KEY="short-secret",
            REDIS_PASSWORD=VALID_REDIS_PASSWORD,
        )

    assert error.value.errors()[0]["loc"] == ("JWT_SECRET_KEY",)


def test_settings_loads_redis_config() -> None:
    settings = Settings(
        _env_file=None,
        JWT_SECRET_KEY=VALID_JWT_SECRET,
        REDIS_HOST="redis",
        REDIS_PORT=6380,
        REDIS_DB=1,
        REDIS_PASSWORD=VALID_REDIS_PASSWORD,
        REDIS_CONNECT_TIMEOUT_SECONDS=0.5,
        REDIS_SOCKET_TIMEOUT_SECONDS=0.75,
    )

    assert settings.REDIS_HOST == "redis"
    assert settings.REDIS_PORT == 6380
    assert settings.REDIS_DB == 1
    assert settings.REDIS_PASSWORD.get_secret_value() == VALID_REDIS_PASSWORD
    assert str(settings.REDIS_PASSWORD) == "**********"
    assert settings.REDIS_CONNECT_TIMEOUT_SECONDS == 0.5
    assert settings.REDIS_SOCKET_TIMEOUT_SECONDS == 0.75


def test_settings_rejects_short_redis_password() -> None:
    with pytest.raises(ValidationError) as error:
        Settings(
            _env_file=None,
            JWT_SECRET_KEY=VALID_JWT_SECRET,
            REDIS_PASSWORD="short",
        )

    assert error.value.errors()[0]["loc"] == ("REDIS_PASSWORD",)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("REDIS_PORT", 0),
        ("REDIS_PORT", 65536),
        ("REDIS_DB", -1),
        ("REDIS_CONNECT_TIMEOUT_SECONDS", 0),
        ("REDIS_SOCKET_TIMEOUT_SECONDS", 0),
    ],
)
def test_settings_rejects_invalid_redis_config(field: str, value: int) -> None:
    with pytest.raises(ValidationError) as error:
        Settings(
            _env_file=None,
            JWT_SECRET_KEY=VALID_JWT_SECRET,
            REDIS_PASSWORD=VALID_REDIS_PASSWORD,
            **{field: value},
        )

    assert error.value.errors()[0]["loc"] == (field,)


def test_settings_loads_login_rate_limit_config() -> None:
    settings = Settings(
        _env_file=None,
        JWT_SECRET_KEY=VALID_JWT_SECRET,
        REDIS_PASSWORD=VALID_REDIS_PASSWORD,
        LOGIN_RATE_LIMIT_MAX_ATTEMPTS=10,
        LOGIN_RATE_LIMIT_WINDOW_SECONDS=120,
    )

    assert settings.LOGIN_RATE_LIMIT_MAX_ATTEMPTS == 10
    assert settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS == 120


@pytest.mark.parametrize(
    "field",
    [
        "LOGIN_RATE_LIMIT_MAX_ATTEMPTS",
        "LOGIN_RATE_LIMIT_WINDOW_SECONDS",
    ],
)
def test_settings_rejects_invalid_login_rate_limit_config(field: str) -> None:
    with pytest.raises(ValidationError) as error:
        Settings(
            _env_file=None,
            JWT_SECRET_KEY=VALID_JWT_SECRET,
            REDIS_PASSWORD=VALID_REDIS_PASSWORD,
            **{field: 0},
        )

    assert error.value.errors()[0]["loc"] == (field,)


def test_settings_loads_session_expiration_config() -> None:
    settings = Settings(
        _env_file=None,
        JWT_SECRET_KEY=VALID_JWT_SECRET,
        REDIS_PASSWORD=VALID_REDIS_PASSWORD,
        SESSION_EXPIRATION_MODE="sliding",
        SESSION_TTL_DAYS=7,
        SESSION_ABSOLUTE_MAX_DAYS=30,
    )

    assert settings.SESSION_EXPIRATION_MODE == "sliding"
    assert settings.SESSION_TTL_DAYS == 7
    assert settings.SESSION_ABSOLUTE_MAX_DAYS == 30


def test_settings_rejects_sliding_ttl_above_absolute_max() -> None:
    with pytest.raises(ValidationError) as error:
        Settings(
            _env_file=None,
            JWT_SECRET_KEY=VALID_JWT_SECRET,
            REDIS_PASSWORD=VALID_REDIS_PASSWORD,
            SESSION_EXPIRATION_MODE="sliding",
            SESSION_TTL_DAYS=30,
            SESSION_ABSOLUTE_MAX_DAYS=7,
        )

    validation_error = error.value.errors()[0]

    assert validation_error["loc"] == ()
    assert (
        "SESSION_ABSOLUTE_MAX_DAYS must be greater than or equal"
        in validation_error["msg"]
    )
