from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings

VALID_JWT_SECRET = "test-only-jwt-secret-key-32-characters"
VALID_REDIS_PASSWORD = "test-only-redis-password"


def test_settings_loads_redis_config() -> None:
    settings = Settings(
        _env_file=None,
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
            REDIS_PASSWORD=VALID_REDIS_PASSWORD,
            **{field: value},
        )

    assert error.value.errors()[0]["loc"] == (field,)


def test_settings_loads_login_rate_limit_config() -> None:
    settings = Settings(
        _env_file=None,
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
            REDIS_PASSWORD=VALID_REDIS_PASSWORD,
            **{field: 0},
        )

    assert error.value.errors()[0]["loc"] == (field,)


def test_settings_loads_session_expiration_config() -> None:
    settings = Settings(
        _env_file=None,
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


def test_settings_loads_jwt_key_ring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("JWT_ACTIVE_KEY_ID")
    monkeypatch.delenv("JWT_SIGNING_KEYS")

    second_secret = "test-only-jwt-secret-key-v2-32-characters"

    settings = Settings(
        _env_file=None,
        JWT_ACTIVE_KEY_ID="v2",
        JWT_SIGNING_KEYS={
            "v1": VALID_JWT_SECRET,
            "v2": second_secret,
        },
        REDIS_PASSWORD=VALID_REDIS_PASSWORD,
    )

    assert settings.JWT_ACTIVE_KEY_ID == "v2"
    assert set(settings.JWT_SIGNING_KEYS) == {"v1", "v2"}
    assert settings.JWT_SIGNING_KEYS["v2"].get_secret_value() == second_secret
    assert str(settings.JWT_SIGNING_KEYS["v2"]) == "**********"


def test_settings_rejects_active_jwt_key_missing_from_key_ring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("JWT_ACTIVE_KEY_ID")
    monkeypatch.delenv("JWT_SIGNING_KEYS")

    with pytest.raises(ValidationError) as error:
        Settings(
            _env_file=None,
            JWT_ACTIVE_KEY_ID="v2",
            JWT_SIGNING_KEYS={
                "v1": VALID_JWT_SECRET,
            },
            REDIS_PASSWORD=VALID_REDIS_PASSWORD,
        )

    validation_error = error.value.errors()[0]

    assert validation_error["loc"] == ()
    assert "JWT_ACTIVE_KEY_ID must exist in JWT_SIGNING_KEYS" in validation_error["msg"]


def test_settings_rejects_short_jwt_signing_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("JWT_ACTIVE_KEY_ID")
    monkeypatch.delenv("JWT_SIGNING_KEYS")

    with pytest.raises(ValidationError) as error:
        Settings(
            _env_file=None,
            JWT_ACTIVE_KEY_ID="v1",
            JWT_SIGNING_KEYS={
                "v1": "short-secret",
            },
            REDIS_PASSWORD=VALID_REDIS_PASSWORD,
        )

    assert error.value.errors()[0]["loc"] == (
        "JWT_SIGNING_KEYS",
        "v1",
    )


def test_settings_rejects_invalid_jwt_key_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("JWT_ACTIVE_KEY_ID")
    monkeypatch.delenv("JWT_SIGNING_KEYS")

    with pytest.raises(ValidationError) as error:
        Settings(
            _env_file=None,
            JWT_ACTIVE_KEY_ID="invalid key",
            JWT_SIGNING_KEYS={
                "invalid key": VALID_JWT_SECRET,
            },
            REDIS_PASSWORD=VALID_REDIS_PASSWORD,
        )

    validation_locations = {
        validation_error["loc"] for validation_error in error.value.errors()
    }

    assert ("JWT_ACTIVE_KEY_ID",) in validation_locations
    assert any(location[0] == "JWT_SIGNING_KEYS" for location in validation_locations)


def test_settings_loads_storage_config() -> None:
    settings = Settings(
        _env_file=None,
        REDIS_PASSWORD=VALID_REDIS_PASSWORD,
        STORAGE_PROVIDER="local",
        STORAGE_LOCAL_ROOT=Path("/tmp/storage"),
        MAX_UPLOAD_SIZE_BYTES=10 * 1024 * 1024,
        UPLOAD_CHUNK_SIZE_BYTES=512 * 1024,
    )

    assert settings.STORAGE_PROVIDER == "local"
    assert settings.STORAGE_LOCAL_ROOT == Path("/tmp/storage")
    assert settings.MAX_UPLOAD_SIZE_BYTES == 10 * 1024 * 1024
    assert settings.UPLOAD_CHUNK_SIZE_BYTES == 512 * 1024


def test_settings_rejects_chunk_size_above_upload_limit() -> None:
    with pytest.raises(ValidationError) as error:
        Settings(
            _env_file=None,
            REDIS_PASSWORD=VALID_REDIS_PASSWORD,
            STORAGE_PROVIDER="local",
            MAX_UPLOAD_SIZE_BYTES=1024 * 1024,
            UPLOAD_CHUNK_SIZE_BYTES=2 * 1024 * 1024,
        )

    validation_error = error.value.errors()[0]

    assert validation_error["loc"] == ()
    assert (
        "UPLOAD_CHUNK_SIZE_BYTES must be less than or equal to MAX_UPLOAD_SIZE_BYTES"
        in validation_error["msg"]
    )


def test_settings_loads_minio_storage_config() -> None:
    settings = Settings(
        _env_file=None,
        REDIS_PASSWORD=VALID_REDIS_PASSWORD,
        STORAGE_PROVIDER="minio",
        STORAGE_MINIO_ENDPOINT="http://127.0.0.1:9000",
        STORAGE_MINIO_ACCESS_KEY="test-app",
        STORAGE_MINIO_SECRET_KEY="test-minio-secret",
        STORAGE_MINIO_BUCKET="test-files",
    )

    assert settings.STORAGE_PROVIDER == "minio"
    assert str(settings.STORAGE_MINIO_ENDPOINT) == "http://127.0.0.1:9000/"
    assert settings.STORAGE_MINIO_ACCESS_KEY == "test-app"
    assert settings.STORAGE_MINIO_SECRET_KEY.get_secret_value() == "test-minio-secret"
    assert str(settings.STORAGE_MINIO_SECRET_KEY) == "**********"
    assert settings.STORAGE_MINIO_BUCKET == "test-files"


def test_settings_rejects_incomplete_minio_config() -> None:
    with pytest.raises(ValidationError) as error:
        Settings(
            _env_file=None,
            REDIS_PASSWORD=VALID_REDIS_PASSWORD,
            STORAGE_PROVIDER="minio",
        )

    validation_error = error.value.errors()[0]

    assert validation_error["loc"] == ()
    assert "MinIO storage requires" in validation_error["msg"]
    assert "STORAGE_MINIO_ENDPOINT" in validation_error["msg"]
    assert "STORAGE_MINIO_ACCESS_KEY" in validation_error["msg"]
    assert "STORAGE_MINIO_SECRET_KEY" in validation_error["msg"]
    assert "STORAGE_MINIO_BUCKET" in validation_error["msg"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("STORAGE_MINIO_ENDPOINT", "not-a-url"),
        ("STORAGE_MINIO_ACCESS_KEY", "ab"),
        ("STORAGE_MINIO_SECRET_KEY", "short"),
        ("STORAGE_MINIO_BUCKET", "Invalid_Bucket"),
    ],
)
def test_settings_rejects_invalid_minio_config(
    field: str,
    value: str,
) -> None:
    minio_config = {
        "STORAGE_PROVIDER": "minio",
        "STORAGE_MINIO_ENDPOINT": "http://127.0.0.1:9000",
        "STORAGE_MINIO_ACCESS_KEY": "test-app",
        "STORAGE_MINIO_SECRET_KEY": "test-minio-secret",
        "STORAGE_MINIO_BUCKET": "test-files",
    }
    minio_config[field] = value

    with pytest.raises(ValidationError) as error:
        Settings(
            _env_file=None,
            REDIS_PASSWORD=VALID_REDIS_PASSWORD,
            **minio_config,
        )

    assert error.value.errors()[0]["loc"] == (field,)


def test_settings_defaults_to_empty_ai_provider_registry() -> None:
    settings = Settings(
        _env_file=None,
        REDIS_PASSWORD=VALID_REDIS_PASSWORD,
        AI_PROVIDERS={},
    )

    assert settings.AI_PROVIDERS == {}


def test_settings_loads_multiple_ai_provider_configs() -> None:
    primary_api_key = "test-primary-api-key"
    backup_api_key = "test-backup-api-key"

    settings = Settings(
        _env_file=None,
        REDIS_PASSWORD=VALID_REDIS_PASSWORD,
        AI_PROVIDERS={
            "primary": {
                "provider_type": "openai_compatible",
                "api_key": primary_api_key,
                "base_url": "https://primary.example.com/v1",
                "connect_timeout_seconds": 0.5,
                "read_timeout_seconds": 1.25,
            },
            "backup": {
                "provider_type": "openai_compatible",
                "api_key": backup_api_key,
                "base_url": "https://backup.example.com/v1",
            },
        },
    )

    assert set(settings.AI_PROVIDERS) == {"primary", "backup"}

    primary = settings.AI_PROVIDERS["primary"]
    assert primary.provider_type == "openai_compatible"
    assert primary.api_key.get_secret_value() == primary_api_key
    assert str(primary.api_key) == "**********"
    assert str(primary.base_url) == "https://primary.example.com/v1"
    assert primary.connect_timeout_seconds == 0.5
    assert primary.read_timeout_seconds == 1.25

    backup = settings.AI_PROVIDERS["backup"]
    assert backup.api_key.get_secret_value() == backup_api_key
    assert str(backup.api_key) == "**********"
    assert backup.connect_timeout_seconds == 5.0
    assert backup.read_timeout_seconds == 60.0

    settings_repr = repr(settings.AI_PROVIDERS)
    assert primary_api_key not in settings_repr
    assert backup_api_key not in settings_repr


def test_settings_parses_ai_providers_from_json_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "AI_PROVIDERS",
        '{"primary":{"provider_type":"openai_compatible",'
        '"api_key":"test-env-api-key",'
        '"base_url":"https://api.example.com/v1"}}',
    )

    settings = Settings(
        _env_file=None,
        REDIS_PASSWORD=VALID_REDIS_PASSWORD,
    )

    provider = settings.AI_PROVIDERS["primary"]
    assert provider.provider_type == "openai_compatible"
    assert provider.api_key.get_secret_value() == "test-env-api-key"
    assert str(provider.base_url) == "https://api.example.com/v1"


@pytest.mark.parametrize(
    "missing_field",
    [
        "provider_type",
        "api_key",
        "base_url",
    ],
)
def test_settings_rejects_incomplete_ai_provider_config(
    missing_field: str,
) -> None:
    provider_config: dict[str, object] = {
        "provider_type": "openai_compatible",
        "api_key": "test-ai-api-key",
        "base_url": "https://api.example.com/v1",
    }
    provider_config.pop(missing_field)

    with pytest.raises(ValidationError) as error:
        Settings(
            _env_file=None,
            REDIS_PASSWORD=VALID_REDIS_PASSWORD,
            AI_PROVIDERS={"primary": provider_config},
        )

    assert error.value.errors()[0]["loc"] == (
        "AI_PROVIDERS",
        "primary",
        missing_field,
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider_type", "unknown_provider"),
        ("api_key", ""),
        ("base_url", "not-a-url"),
        ("connect_timeout_seconds", 0),
        ("read_timeout_seconds", 0),
    ],
)
def test_settings_rejects_invalid_ai_provider_config(
    field: str,
    value: str | int,
) -> None:
    provider_config: dict[str, object] = {
        "provider_type": "openai_compatible",
        "api_key": "test-ai-api-key",
        "base_url": "https://api.example.com/v1",
        "connect_timeout_seconds": 5,
        "read_timeout_seconds": 60,
    }
    provider_config[field] = value

    with pytest.raises(ValidationError) as error:
        Settings(
            _env_file=None,
            REDIS_PASSWORD=VALID_REDIS_PASSWORD,
            AI_PROVIDERS={"primary": provider_config},
        )

    assert error.value.errors()[0]["loc"] == (
        "AI_PROVIDERS",
        "primary",
        field,
    )
