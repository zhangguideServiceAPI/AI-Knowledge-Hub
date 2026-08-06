import os
from collections.abc import Generator
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

os.environ["JWT_SECRET_KEY"] = "test-only-jwt-secret-key-32-characters"
if os.getenv("RUN_REDIS_INTEGRATION_TESTS") != "1":
    os.environ["REDIS_PASSWORD"] = "test-only-redis-password"

from app.api.dependencies import get_login_rate_limiter, get_session_repository
from app.db.base import Base
from app.db.repositories.session_repository import SessionRepository
from app.db.session import get_db
from app.main import app
from app.services.login_rate_limiter import LoginRateLimiter


@pytest.fixture
def session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)

    with Session(bind=engine) as session:
        yield session

    engine.dispose()


@pytest.fixture
def client(
    session: Session,
    login_rate_limiter: Mock,
    session_repository: Mock,
) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_login_rate_limiter] = lambda: login_rate_limiter
    app.dependency_overrides[get_session_repository] = lambda: session_repository

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_login_rate_limiter, None)
    app.dependency_overrides.pop(get_session_repository, None)


@pytest.fixture
def login_rate_limiter() -> Mock:
    limiter = Mock(spec=LoginRateLimiter)
    limiter.is_limited.return_value = False
    return limiter


@pytest.fixture
def session_repository() -> Mock:
    return Mock(spec=SessionRepository)
