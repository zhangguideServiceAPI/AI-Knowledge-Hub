"""Workflow 的恢复用例：权限、重试策略与短事务由 Service 统一编排。"""

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.repositories.knowledge_repository import KnowledgeRepository
from app.db.repositories.knowledge_revision_repository import (
    KnowledgeRevisionRepository,
)
from app.db.repositories.workflow_repository import WorkflowRepository
from app.models.document_version import DocumentVersionStatus
from app.models.knowledge_revision import KnowledgeRevision, KnowledgeRevisionStatus
from app.models.workflow import WorkflowRun, WorkflowStepRun
from app.workflow.exceptions import (
    WorkflowApprovalConflictError,
    WorkflowRetryExhaustedError,
    WorkflowRunNotFoundError,
    WorkflowRunNotRetryableError,
)
from app.workflow.registry import WorkflowDefinitionRegistry
from app.workflow.routing import WorkflowRouteResolver
from app.workflow.state_machine import WorkflowRunStatus, WorkflowStepRunStatus

_RETRYABLE_FAILURE_CODES = frozenset({"node_retryable"})


@dataclass(frozen=True)
class WorkflowResumeResult:
    """一次 resume 的结果：是否实际重开，以及当前 Run/Step 的持久化事实。"""

    run: WorkflowRun
    step: WorkflowStepRun | None
    resumed: bool


@dataclass(frozen=True)
class ApprovalDecisionResult:
    """一次审批或过期裁决后的 Revision、Run 与是否实际写入决定。"""

    revision: KnowledgeRevision
    run: WorkflowRun
    applied: bool


class WorkflowService:
    """协调 Workflow 恢复，不执行 Node、不开启外部网络调用。"""

    def __init__(
        self, session: Session, definition_registry: WorkflowDefinitionRegistry
    ) -> None:
        """注入请求 Session 与已验证 Definition Registry；Repository 保持只做数据访问。"""

        self._session = session
        self._repository = WorkflowRepository(session)
        self._knowledge_repository = KnowledgeRepository(session)
        self._revision_repository = KnowledgeRevisionRepository(session)
        self._definition_registry = definition_registry
        self._route_resolver = WorkflowRouteResolver()

    def submit_revision_for_approval(
        self,
        *,
        owner_id: int,
        document_id: str,
        document_version_id: str,
        definition_key: str,
        definition_version: int,
        expires_at: datetime,
    ) -> ApprovalDecisionResult:
        """为 pending Version 创建 submitted Revision、waiting Run 与无 Attempt 的等待 Step。"""

        document = self._knowledge_repository.get_owned_document(
            document_id=document_id, owner_id=owner_id
        )
        if document is None:
            raise WorkflowRunNotFoundError()
        version = self._knowledge_repository.get_version_for_document(
            document_id=document.id, document_version_id=document_version_id
        )
        if version is None or version.status != DocumentVersionStatus.PENDING.value:
            raise WorkflowApprovalConflictError(
                "DocumentVersion is not pending approval."
            )
        definition = self._definition_registry.get(definition_key, definition_version)
        start_step = definition.step_by_id(definition.start_step_id)
        revision_id = str(uuid4())
        try:
            run = self._repository.create_run(
                WorkflowRun(
                    owner_id=owner_id,
                    definition_key=definition.key,
                    definition_version=definition.version,
                    run_input={
                        "revision_id": revision_id,
                        "document_id": document.id,
                        "document_version_id": version.id,
                    },
                    status=WorkflowRunStatus.WAITING_APPROVAL.value,
                )
            )
            self._repository.create_step(
                WorkflowStepRun(
                    workflow_run_id=run.id,
                    step_id=start_step.step_id,
                    step_index=0,
                    status=WorkflowStepRunStatus.WAITING.value,
                )
            )
            revision = self._revision_repository.create(
                KnowledgeRevision(
                    id=revision_id,
                    owner_id=owner_id,
                    document_id=document.id,
                    document_version_id=version.id,
                    workflow_run_id=run.id,
                    expires_at=expires_at,
                )
            )
            self._session.commit()
        except SQLAlchemyError:
            self._session.rollback()
            raise
        return ApprovalDecisionResult(revision=revision, run=run, applied=True)

    def approve_revision(
        self, *, owner_id: int, revision_id: str, approver_id: int
    ) -> ApprovalDecisionResult:
        """原子批准 Revision，完成等待 Step 并创建固定 approved 后继 Step。"""

        return self._decide_revision(
            owner_id=owner_id,
            revision_id=revision_id,
            decision=KnowledgeRevisionStatus.APPROVED,
            decided_by=approver_id,
        )

    def reject_revision(
        self, *, owner_id: int, revision_id: str, approver_id: int
    ) -> ApprovalDecisionResult:
        """原子拒绝 Revision，并取消 waiting Run/Step；人工等待本身不产生 Attempt。"""

        return self._decide_revision(
            owner_id=owner_id,
            revision_id=revision_id,
            decision=KnowledgeRevisionStatus.REJECTED,
            decided_by=approver_id,
        )

    def reconcile_expired_revision(
        self, *, owner_id: int, revision_id: str, now: datetime
    ) -> ApprovalDecisionResult:
        """在读取或操作时惰性收口过期 Revision，不依赖 Scheduler。"""

        revision = self._get_owned_revision(owner_id=owner_id, revision_id=revision_id)
        run = self._get_owned_run(owner_id=owner_id, run_id=revision.workflow_run_id)
        if not self._revision_repository.is_submitted_and_expired(revision, now=now):
            return ApprovalDecisionResult(revision=revision, run=run, applied=False)
        return self._decide_revision(
            owner_id=owner_id,
            revision_id=revision_id,
            decision=KnowledgeRevisionStatus.EXPIRED,
            decided_by=None,
        )

    def resume_failed_run(self, *, owner_id: int, run_id: str) -> WorkflowResumeResult:
        """只将可重试失败 Run 的最早失败 Step 重排队；成功/进行中 Run 不会重放。"""

        run = self._get_owned_run(owner_id=owner_id, run_id=run_id)
        status = WorkflowRunStatus(run.status)
        if status is WorkflowRunStatus.SUCCEEDED:
            return WorkflowResumeResult(run=run, step=None, resumed=False)
        if status is WorkflowRunStatus.RUNNING:
            return WorkflowResumeResult(run=run, step=None, resumed=False)
        if status is not WorkflowRunStatus.FAILED:
            raise WorkflowRunNotRetryableError("WorkflowRun is not resumable.")
        if run.failure_code not in _RETRYABLE_FAILURE_CODES:
            raise WorkflowRunNotRetryableError("Workflow failure is not retryable.")

        step = self._repository.get_failed_step(run.id)
        if step is None:
            raise WorkflowRunNotRetryableError(
                "WorkflowRun has no failed Step to resume."
            )
        definition = self._definition_registry.get(
            run.definition_key, run.definition_version
        )
        definition_step = definition.step_by_id(step.step_id)
        if self._repository.get_attempt_count(step.id) >= definition_step.max_attempts:
            raise WorkflowRetryExhaustedError("Workflow Step retry limit is exhausted.")

        try:
            resumed = self._repository.requeue_failed_run_and_step(
                run_id=run.id, step_id=step.id
            )
            if resumed:
                self._session.commit()
                return WorkflowResumeResult(run=run, step=step, resumed=True)
            self._session.rollback()
        except SQLAlchemyError:
            self._session.rollback()
            raise

        current = self._get_owned_run(owner_id=owner_id, run_id=run_id)
        if WorkflowRunStatus(current.status) in {
            WorkflowRunStatus.RUNNING,
            WorkflowRunStatus.SUCCEEDED,
        }:
            return WorkflowResumeResult(run=current, step=None, resumed=False)
        raise WorkflowRunNotRetryableError("WorkflowRun changed during resume.")

    def _get_owned_run(self, *, owner_id: int, run_id: str) -> WorkflowRun:
        """读取当前用户的 Run；查不到时不区分不存在与越权。"""

        run = self._repository.get_owned_run(run_id=run_id, owner_id=owner_id)
        if run is None:
            raise WorkflowRunNotFoundError()
        return run

    def _get_owned_revision(
        self, *, owner_id: int, revision_id: str
    ) -> KnowledgeRevision:
        """读取当前所有者的 Revision；不存在与越权均不暴露细节。"""

        revision = self._revision_repository.get_owned(
            revision_id=revision_id, owner_id=owner_id
        )
        if revision is None:
            raise WorkflowRunNotFoundError()
        return revision

    def _decide_revision(
        self,
        *,
        owner_id: int,
        revision_id: str,
        decision: KnowledgeRevisionStatus,
        decided_by: int | None,
    ) -> ApprovalDecisionResult:
        """统一执行批准、拒绝或过期的 Revision/Workflow 条件状态迁移。"""

        revision = self._get_owned_revision(owner_id=owner_id, revision_id=revision_id)
        run = self._get_owned_run(owner_id=owner_id, run_id=revision.workflow_run_id)
        if revision.status != KnowledgeRevisionStatus.SUBMITTED.value:
            if revision.status == decision.value:
                return ApprovalDecisionResult(revision=revision, run=run, applied=False)
            raise WorkflowApprovalConflictError("Revision has already been decided.")
        definition = self._definition_registry.get(
            run.definition_key, run.definition_version
        )
        waiting_step = self._repository.get_step(
            run_id=run.id, step_id=definition.start_step_id
        )
        if waiting_step is None:
            raise WorkflowApprovalConflictError(
                "WorkflowRun has no waiting approval Step."
            )

        try:
            revision_changed = self._revision_repository.update_submitted_decision(
                revision_id=revision.id, status=decision, decided_by=decided_by
            )
            if decision is KnowledgeRevisionStatus.APPROVED:
                decision_output = {"decision": "approved", "approved_by": decided_by}
                run_changed = self._repository.approve_waiting_run_and_step(
                    run_id=run.id,
                    step_id=waiting_step.id,
                    output_payload=decision_output,
                )
                next_step_id = self._route_resolver.select_next_step_id(
                    definition.step_by_id(waiting_step.step_id),
                    node_output=decision_output,
                )
                if next_step_id is not None:
                    next_index = next(
                        index
                        for index, step in enumerate(definition.steps)
                        if step.step_id == next_step_id
                    )
                    self._repository.create_step(
                        WorkflowStepRun(
                            workflow_run_id=run.id,
                            step_id=next_step_id,
                            step_index=next_index,
                        )
                    )
            else:
                run_changed = self._repository.cancel_waiting_run_and_step(
                    run_id=run.id, step_id=waiting_step.id
                )
            if revision_changed and run_changed:
                self._session.commit()
                return ApprovalDecisionResult(revision=revision, run=run, applied=True)
            self._session.rollback()
        except SQLAlchemyError:
            self._session.rollback()
            raise

        current_revision = self._get_owned_revision(
            owner_id=owner_id, revision_id=revision_id
        )
        current_run = self._get_owned_run(
            owner_id=owner_id, run_id=revision.workflow_run_id
        )
        if current_revision.status == decision.value:
            return ApprovalDecisionResult(
                revision=current_revision, run=current_run, applied=False
            )
        raise WorkflowApprovalConflictError("Revision changed during decision.")
