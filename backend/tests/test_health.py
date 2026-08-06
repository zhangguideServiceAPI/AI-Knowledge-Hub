import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.health import ReadinessResponse

client = TestClient(app)


def test_liveness_returns_ok() -> None:
    response = client.get("/health/live")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "ok"}


def test_readiness_returns_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    monkeypatch.setattr(
        "app.api.health.get_application_readiness",
        lambda: ReadinessResponse(
            status="ready",
            database="ok",
            redis="ok",
        ),
    )

    response = client.get("/health/ready")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "status": "ready",
        "database": "ok",
        "redis": "ok",
    }


def test_readiness_returns_unavailable_when_redis_is_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    monkeypatch.setattr(
        "app.api.health.get_application_readiness",
        lambda: ReadinessResponse(
            status="not_ready",
            database="ok",
            redis="unavailable",
        ),
    )

    response = client.get("/health/ready")

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json() == {
        "status": "not_ready",
        "database": "ok",
        "redis": "unavailable",
    }


def test_readiness_returns_unavailable_when_database_is_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.api.health.get_application_readiness",
        lambda: ReadinessResponse(
            status="not_ready",
            database="unavailable",
            redis="ok",
        ),
    )

    response = client.get("/health/ready")

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json() == {
        "status": "not_ready",
        "database": "unavailable",
        "redis": "ok",
    }
