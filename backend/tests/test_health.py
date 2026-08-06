import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_liveness_returns_ok() -> None:
    response = client.get("/health/live")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "ok"}


def test_readiness_returns_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    monkeypatch.setattr(
        "app.api.health.is_application_ready",
        lambda: True,
    )

    response = client.get("/health/ready")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "ready", "database": "ok"}


def test_readiness_returns_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    monkeypatch.setattr(
        "app.api.health.is_application_ready",
        lambda: False,
    )

    response = client.get("/health/ready")

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json() == {"status": "not_ready", "database": "unavailable"}
