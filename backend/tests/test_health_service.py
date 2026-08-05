import pytest

from app.services.health_service import get_application_readiness


@pytest.mark.parametrize(
    ("database_ready", "redis_ready", "storage_ready", "expected"),
    [
        (
            True,
            True,
            True,
            {
                "status": "ready",
                "database": "ok",
                "redis": "ok",
                "storage": "ok",
            },
        ),
        (
            False,
            True,
            True,
            {
                "status": "not_ready",
                "database": "unavailable",
                "redis": "ok",
                "storage": "ok",
            },
        ),
        (
            True,
            False,
            True,
            {
                "status": "not_ready",
                "database": "ok",
                "redis": "unavailable",
                "storage": "ok",
            },
        ),
        (
            True,
            True,
            False,
            {
                "status": "not_ready",
                "database": "ok",
                "redis": "ok",
                "storage": "unavailable",
            },
        ),
        (
            False,
            False,
            False,
            {
                "status": "not_ready",
                "database": "unavailable",
                "redis": "unavailable",
                "storage": "unavailable",
            },
        ),
    ],
)
def test_get_application_readiness(
    monkeypatch: pytest.MonkeyPatch,
    database_ready: bool,
    redis_ready: bool,
    storage_ready: bool,
    expected: dict[str, str],
) -> None:
    monkeypatch.setattr(
        "app.services.health_service.is_database_ready",
        lambda: database_ready,
    )
    monkeypatch.setattr(
        "app.services.health_service.is_redis_ready",
        lambda: redis_ready,
    )
    monkeypatch.setattr(
        "app.services.health_service.is_storage_ready",
        lambda: storage_ready,
    )

    readiness = get_application_readiness()

    assert readiness.model_dump() == expected
