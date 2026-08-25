"""知识修订审批事实的数据访问；调用方拥有事务边界。"""

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.knowledge_revision import KnowledgeRevision, KnowledgeRevisionStatus


class KnowledgeRevisionRepository:
    """封装 Revision 的所有者读取、创建与条件业务状态迁移。"""

    def __init__(self, session: Session) -> None:
        """保存当前业务短事务使用的 Session。"""

        self._session = session

    def create(self, revision: KnowledgeRevision) -> KnowledgeRevision:
        """写入 Revision 并 flush，使调用方可在同一事务继续建立 Run 外键。"""

        self._session.add(revision)
        self._session.flush()
        self._session.refresh(revision)
        return revision

    def get_owned(self, *, revision_id: str, owner_id: int) -> KnowledgeRevision | None:
        """读取当前所有者的 Revision，避免向上层泄露越权审批事实。"""

        statement = select(KnowledgeRevision).where(
            KnowledgeRevision.id == revision_id,
            KnowledgeRevision.owner_id == owner_id,
        )
        return self._session.scalar(statement)

    def update_submitted_decision(
        self,
        *,
        revision_id: str,
        status: KnowledgeRevisionStatus,
        decided_by: int | None,
    ) -> bool:
        """仅将 submitted Revision 原子裁决为 approved、rejected 或 expired。"""

        if status not in {
            KnowledgeRevisionStatus.APPROVED,
            KnowledgeRevisionStatus.REJECTED,
            KnowledgeRevisionStatus.EXPIRED,
        }:
            raise ValueError("Revision decision must be a terminal approval status.")
        result = self._session.execute(
            update(KnowledgeRevision)
            .where(
                KnowledgeRevision.id == revision_id,
                KnowledgeRevision.status == KnowledgeRevisionStatus.SUBMITTED.value,
            )
            .values(status=status.value, decided_by=decided_by, decided_at=func.now())
        )
        return result.rowcount == 1

    def is_submitted_and_expired(
        self, revision: KnowledgeRevision, *, now: datetime
    ) -> bool:
        """判断已读取 Revision 是否仍 submitted 且到达惰性过期边界。"""

        return (
            revision.status == KnowledgeRevisionStatus.SUBMITTED.value
            and revision.expires_at <= now
        )
