from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import aliased
from sqlalchemy.orm import Session

from app.models.document_chunk import DocumentChunk
from app.models.document_version import DocumentVersion, DocumentVersionStatus
from app.models.file_resource import FileResource, FileStatus
from app.models.knowledge_base import KnowledgeBase
from app.models.knowledge_document import KnowledgeDocument


class KnowledgeRepository:
    """Database queries owned by the Knowledge domain."""

    def __init__(self, session: Session) -> None:
        """保存调用方传入的 SQLAlchemy Session，供本仓储执行知识域查询。"""

        self._session = session

    def get_owned_base(
        self,
        *,
        knowledge_base_id: str,
        owner_id: int,
    ) -> KnowledgeBase | None:
        """按知识库 ID 和 owner 查询可访问的 KnowledgeBase；未找到时返回 None。"""

        # select(...) 只构造 SQL 查询；session.scalar(...) 才执行查询并取第一条结果。
        statement = select(KnowledgeBase).where(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.owner_id == owner_id,
        )
        return self._session.scalar(statement)

    def get_document_by_base_and_file(
        self,
        *,
        knowledge_base_id: str,
        file_id: str,
    ) -> KnowledgeDocument | None:
        """查询某知识库中对某 FileResource 的既有 Document，支持重复请求幂等。"""

        statement = select(KnowledgeDocument).where(
            KnowledgeDocument.knowledge_base_id == knowledge_base_id,
            KnowledgeDocument.file_id == file_id,
        )
        return self._session.scalar(statement)

    def get_owned_document(
        self,
        *,
        document_id: str,
        owner_id: int,
    ) -> KnowledgeDocument | None:
        """
        查询当前用户可处理的 Document。

        同时验证知识库所有权、文件所有权、文件 READY 状态和未删除条件；
        任一条件不满足均返回 None，不向 Service 暴露越权或不可用资源。
        """

        # join 把 Document、KnowledgeBase 和 FileResource 放进同一条查询；
        # 权限和 READY 状态在数据库查询阶段完成，调用方不会先拿到越权文件。
        statement = (
            select(KnowledgeDocument)
            .join(
                KnowledgeBase,
                KnowledgeDocument.knowledge_base_id == KnowledgeBase.id,
            )
            .join(FileResource, KnowledgeDocument.file_id == FileResource.id)
            .where(
                KnowledgeDocument.id == document_id,
                KnowledgeBase.owner_id == owner_id,
                FileResource.owner_id == owner_id,
                FileResource.status == FileStatus.READY.value,
                FileResource.deleted_at.is_(None),
            )
        )
        return self._session.scalar(statement)

    def create_document(
        self,
        document: KnowledgeDocument,
    ) -> KnowledgeDocument:
        """将新 Document 加入当前事务并刷新数据库默认字段，调用方决定何时提交。"""

        self._session.add(document)
        # flush 把 INSERT 发给数据库但不提交事务；这样可立刻拿到 UUID 和数据库默认时间。
        self._session.flush()
        # refresh 从数据库重新读取 server_default 等由数据库生成的字段。
        self._session.refresh(document)
        return document

    def create_base(self, knowledge_base: KnowledgeBase) -> KnowledgeBase:
        """将新 KnowledgeBase 加入当前事务并刷新数据库生成的默认字段。"""

        self._session.add(knowledge_base)
        # flush 发送 INSERT 但不提交；refresh 重新读取 UUID、created_at 等数据库字段。
        self._session.flush()
        self._session.refresh(knowledge_base)
        return knowledge_base

    def get_version_by_fingerprint(
        self,
        *,
        document_id: str,
        processing_fingerprint: str,
    ) -> DocumentVersion | None:
        """按处理指纹查找一个 Document 的既有 Version，用于幂等复用。"""

        # 指纹是一次处理配置的稳定标识；命中后复用旧 Version，避免重复建索引。
        statement = select(DocumentVersion).where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.processing_fingerprint == processing_fingerprint,
        )
        return self._session.scalar(statement)

    def get_version_for_document(
        self,
        *,
        document_id: str,
        document_version_id: str,
    ) -> DocumentVersion | None:
        """查询指定 Document 下的一个 Version，供 Service 校验状态和组织重试。"""

        statement = (
            select(DocumentVersion)
            .where(
                DocumentVersion.id == document_version_id,
                DocumentVersion.document_id == document_id,
            )
            .execution_options(populate_existing=True)
        )
        return self._session.scalar(statement)

    def get_next_version_number(self, *, document_id: str) -> int:
        """返回某个 Document 下一个可用的连续版本号。"""

        # 数据库只返回当前最大版本号；第一个版本从 1 开始。
        latest_number = self._session.scalar(
            select(func.max(DocumentVersion.version_number)).where(
                DocumentVersion.document_id == document_id
            )
        )
        return (latest_number or 0) + 1

    def create_version(self, version: DocumentVersion) -> DocumentVersion:
        """把 Version 写入当前事务，并取得数据库/默认生成的字段。"""

        self._session.add(version)
        # flush 先发送 INSERT，让后续 Chunk 可以引用这个 Version；commit 仍由 Service 控制。
        self._session.flush()
        self._session.refresh(version)
        return version

    def claim_pending_version(
        self,
        *,
        document_id: str,
        document_version_id: str,
    ) -> DocumentVersion | None:
        """
        原子地将一个 pending Version 认领为 processing，防止重复索引。

        只有 ID、所属 Document 与当前状态同时匹配时才更新；成功返回已刷新状态的
        Version，未命中返回 None。调用方负责 commit 或 rollback，此方法不执行
        网络 I/O，也不读取或修改 Chunk、Qdrant 与 active_version_id。
        """

        # 单条带 status 条件的 UPDATE 是 compare-and-set：并发请求中只有一个 rowcount 为 1。
        statement = (
            update(DocumentVersion)
            .where(
                DocumentVersion.id == document_version_id,
                DocumentVersion.document_id == document_id,
                DocumentVersion.status == DocumentVersionStatus.PENDING.value,
            )
            .values(
                status=DocumentVersionStatus.PROCESSING.value,
                # processing 不是失败状态，必须清除旧的失败原因以满足数据库 CheckConstraint。
                failure_reason=None,
            )
        )
        result = self._session.execute(statement)
        if result.rowcount != 1:
            return None

        statement = (
            select(DocumentVersion)
            .where(DocumentVersion.id == document_version_id)
            # 强制从数据库读取，避免 Session Identity Map 返回更新前的旧对象状态。
            .execution_options(populate_existing=True)
        )
        return self._session.scalar(statement)

    def complete_processing_version(
        self,
        *,
        document_id: str,
        document_version_id: str,
    ) -> DocumentVersion | None:
        """
        原子地将一个 processing Version 标记为 indexed，并返回刷新后的 Version。

        只有当前仍为 processing 的 Version 可以完成；未命中时返回 None，防止重复
        完成或覆盖失败终态。调用方负责在同一个事务中决定是否将该 Version 激活，
        并最终 commit 或 rollback。
        """

        statement = (
            update(DocumentVersion)
            .where(
                DocumentVersion.id == document_version_id,
                DocumentVersion.document_id == document_id,
                DocumentVersion.status == DocumentVersionStatus.PROCESSING.value,
            )
            .values(
                status=DocumentVersionStatus.INDEXED.value,
                failure_reason=None,
            )
        )
        result = self._session.execute(statement)
        if result.rowcount != 1:
            return None

        statement = (
            select(DocumentVersion)
            .where(DocumentVersion.id == document_version_id)
            .execution_options(populate_existing=True)
        )
        return self._session.scalar(statement)

    def fail_processing_version(
        self,
        *,
        document_id: str,
        document_version_id: str,
        target_status: DocumentVersionStatus,
        failure_reason: str,
    ) -> DocumentVersion | None:
        """
        将一个 processing Version 原子标记为 failed 或 cleanup_required。

        输入 target_status 只能是两个失败终态，failure_reason 用于后续诊断和重试决策。
        Version 已完成、已失败或不属于指定 Document 时返回 None，避免重复请求覆盖已有
        终态。调用方负责 commit 或 rollback，本方法不触碰 Document.active_version_id。
        """

        if target_status not in {
            DocumentVersionStatus.FAILED,
            DocumentVersionStatus.CLEANUP_REQUIRED,
        }:
            raise ValueError("Target status must be a document version failure state.")
        if not failure_reason.strip() or len(failure_reason) > 64:
            raise ValueError(
                "Failure reason must be non-empty and at most 64 characters."
            )

        statement = (
            update(DocumentVersion)
            .where(
                DocumentVersion.id == document_version_id,
                DocumentVersion.document_id == document_id,
                DocumentVersion.status == DocumentVersionStatus.PROCESSING.value,
            )
            .values(
                status=target_status.value,
                failure_reason=failure_reason,
            )
        )
        result = self._session.execute(statement)
        if result.rowcount != 1:
            return None

        statement = (
            select(DocumentVersion)
            .where(DocumentVersion.id == document_version_id)
            .execution_options(populate_existing=True)
        )
        return self._session.scalar(statement)

    def requeue_failed_version(
        self,
        *,
        document_id: str,
        document_version_id: str,
    ) -> DocumentVersion | None:
        """
        原子地将 failed 或 cleanup_required Version 重新置为 pending。

        调用方必须先完成 cleanup_required 对应的 Qdrant 清理；本方法仅负责 MySQL
        状态迁移。并发请求中只有一个可以成功重置，未命中时返回 None，调用方应读取
        当前状态而不是重复修改。
        """

        statement = (
            update(DocumentVersion)
            .where(
                DocumentVersion.id == document_version_id,
                DocumentVersion.document_id == document_id,
                DocumentVersion.status.in_(
                    (
                        DocumentVersionStatus.FAILED.value,
                        DocumentVersionStatus.CLEANUP_REQUIRED.value,
                    )
                ),
            )
            .values(
                status=DocumentVersionStatus.PENDING.value,
                failure_reason=None,
            )
        )
        result = self._session.execute(statement)
        if result.rowcount != 1:
            return None

        statement = (
            select(DocumentVersion)
            .where(DocumentVersion.id == document_version_id)
            .execution_options(populate_existing=True)
        )
        return self._session.scalar(statement)

    def promote_active_version(
        self,
        *,
        document_id: str,
        document_version_id: str,
        version_number: int,
    ) -> bool:
        """
        仅在候选 Version 比当前 active Version 更新时，更新 Document.active_version_id。

        输入 Version 已由调用方在同一事务中标记为 indexed；返回 True 表示完成激活。
        旧 Version 晚于新 Version 完成时返回 False，保留更高版本的 active 指针，避免
        并发索引结束顺序反转造成回退。
        """

        active_version = aliased(DocumentVersion)
        active_version_number = (
            select(active_version.version_number)
            .where(active_version.id == KnowledgeDocument.active_version_id)
            .scalar_subquery()
        )
        statement = (
            update(KnowledgeDocument)
            .where(
                KnowledgeDocument.id == document_id,
                or_(
                    KnowledgeDocument.active_version_id.is_(None),
                    active_version_number < version_number,
                ),
            )
            .values(active_version_id=document_version_id)
        )
        result = self._session.execute(statement)
        return result.rowcount == 1

    def create_chunks(self, chunks: list[DocumentChunk]) -> list[DocumentChunk]:
        """把同一 Version 的全部 Chunk 加入当前事务，暂不提交。"""

        self._session.add_all(chunks)
        # 一次 flush 写入全部 Chunk；任何一条失败都会由 Service 的事务统一回滚。
        self._session.flush()
        return chunks

    def list_chunks(self, *, document_version_id: str) -> tuple[DocumentChunk, ...]:
        """按原文顺序读取一个 Version 的 Chunk，供幂等请求复用结果。"""

        statement = (
            select(DocumentChunk)
            .where(DocumentChunk.document_version_id == document_version_id)
            .order_by(DocumentChunk.chunk_index)
        )
        return tuple(self._session.scalars(statement))

    def count_chunks(self, *, document_version_id: str) -> int:
        """返回一个 Version 的 Chunk 数量，避免 API 为计数读取全部原文内容。"""

        count = self._session.scalar(
            select(func.count())
            .select_from(DocumentChunk)
            .where(DocumentChunk.document_version_id == document_version_id)
        )
        return int(count or 0)
