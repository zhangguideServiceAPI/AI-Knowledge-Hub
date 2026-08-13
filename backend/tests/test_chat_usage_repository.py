from datetime import datetime

from sqlalchemy.orm import Session

from app.db.repositories.chat_usage_repository import ChatUsageRepository
from app.models.usage import ChatUsage, ChatUsageMode, ChatUsageStatus
from app.models.user import User


def _create_user(session: Session, email: str = "usage@example.com") -> User:
    user = User(email=email, password_hash="hashed-password")
    session.add(user)
    session.flush()
    return user


def _usage(
    *,
    request_id: str,
    user_id: int,
    created_at: datetime,
    status: ChatUsageStatus = ChatUsageStatus.SUCCESS,
) -> ChatUsage:
    successful = status is ChatUsageStatus.SUCCESS
    return ChatUsage(
        request_id=request_id,
        user_id=user_id,
        request_mode=ChatUsageMode.NON_STREAM.value,
        model_alias="general",
        provider="primary",
        provider_model="provider-model",
        prompt_key="assistant",
        prompt_version="v1",
        input_tokens=None,
        output_tokens=None,
        total_tokens=None,
        latency_ms=25,
        time_to_first_token_ms=None,
        status=status.value,
        finish_reason="stop" if successful else None,
        error_code=None if successful else "ai_provider_timeout",
        estimated_cost=None,
        currency=None,
        pricing_version=None,
        created_at=created_at,
        completed_at=created_at,
    )


def test_create_and_get_by_request_id_preserve_unknown_tokens(
    session: Session,
) -> None:
    user = _create_user(session)
    repository = ChatUsageRepository(session)

    created = repository.create(
        _usage(
            request_id="usage-success",
            user_id=user.id,
            created_at=datetime(2026, 8, 13, 12, 0),
        )
    )

    persisted = repository.get_by_request_id("usage-success")

    assert persisted is created
    assert persisted.input_tokens is None
    assert persisted.output_tokens is None
    assert persisted.total_tokens is None
    assert persisted.estimated_cost is None


def test_list_by_user_sorts_terminal_statuses_and_paginates(
    session: Session,
) -> None:
    owner = _create_user(session, "usage-owner@example.com")
    other = _create_user(session, "usage-other@example.com")
    repository = ChatUsageRepository(session)

    records = (
        _usage(
            request_id="old-success",
            user_id=owner.id,
            status=ChatUsageStatus.SUCCESS,
            created_at=datetime(2026, 8, 13, 10, 0),
        ),
        _usage(
            request_id="middle-failed",
            user_id=owner.id,
            status=ChatUsageStatus.FAILED,
            created_at=datetime(2026, 8, 13, 11, 0),
        ),
        _usage(
            request_id="new-cancelled",
            user_id=owner.id,
            status=ChatUsageStatus.CANCELLED,
            created_at=datetime(2026, 8, 13, 12, 0),
        ),
        _usage(
            request_id="other-user",
            user_id=other.id,
            created_at=datetime(2026, 8, 13, 13, 0),
        ),
    )
    for record in records:
        repository.create(record)

    first_page = repository.list_by_user(owner.id, limit=2, offset=0)
    second_page = repository.list_by_user(owner.id, limit=2, offset=2)

    assert [record.request_id for record in first_page] == [
        "new-cancelled",
        "middle-failed",
    ]
    assert [record.request_id for record in second_page] == ["old-success"]


def test_create_can_be_rolled_back(session: Session) -> None:
    user = _create_user(session)
    repository = ChatUsageRepository(session)
    repository.create(
        _usage(
            request_id="usage-rollback",
            user_id=user.id,
            created_at=datetime(2026, 8, 13, 12, 0),
        )
    )

    session.rollback()

    assert repository.get_by_request_id("usage-rollback") is None
