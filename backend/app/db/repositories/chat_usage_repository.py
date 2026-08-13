from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.usage import ChatUsage


class ChatUsageRepository:
    """负责 ChatUsage 的数据库读写，不负责业务终态计算。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, usage: ChatUsage) -> ChatUsage:
        self._session.add(usage)
        self._session.flush()
        self._session.refresh(usage)
        return usage

    def get_by_request_id(self, request_id: str) -> ChatUsage | None:
        statement = select(ChatUsage).where(
            ChatUsage.request_id == request_id,
        )
        return self._session.scalar(statement)

    def list_by_user(
        self,
        user_id: int,
        *,
        limit: int,
        offset: int,
    ) -> list[ChatUsage]:
        statement = (
            select(ChatUsage)
            .where(ChatUsage.user_id == user_id)
            .order_by(
                ChatUsage.created_at.desc(),
                ChatUsage.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return list(self._session.scalars(statement))
