"""Story 6.6 人工审批、惰性过期与索引状态隔离测试。"""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document_version import DocumentVersion, DocumentVersionStatus
from app.models.file_resource import FileResource, FileStatus
from app.models.knowledge_base import KnowledgeBase
from app.models.knowledge_document import KnowledgeDocument
from app.models.knowledge_revision import KnowledgeRevisionStatus
from app.models.user import User
from app.models.workflow import WorkflowAttempt, WorkflowStepRun
from app.services.workflow_service import WorkflowService
from app.workflow.definition import (
    WorkflowBranchCase,
    WorkflowBranchDefinition,
    WorkflowDefinition,
    WorkflowStepDefinition,
)
from app.workflow.node import WorkflowNodeExecutionContext
from app.workflow.registry import WorkflowDefinitionRegistry, WorkflowNodeRegistry
from app.workflow.state_machine import WorkflowRunStatus, WorkflowStepRunStatus


class ApprovalNode:
    """只提供审批 Definition 所需契约的测试 Node，不在审批 Service 中执行。"""

    node_key = "wait_for_approval"
    input_type = dict
    output_type = dict

    def execute(
        self, node_input: dict[str, object], context: WorkflowNodeExecutionContext
    ) -> dict[str, object]:
        """实现 Protocol；人工审批不会通过 Executor 调用这个 Node。"""

        del context
        return node_input


class IndexNode(ApprovalNode):
    """只提供批准后索引 Step 契约的测试 Node。"""

    node_key = "index_and_activate_version"


def _service(session: Session) -> tuple[WorkflowService, User, DocumentVersion]:
    """创建一个已准备 pending Version 和审批 Definition 的最小业务环境。"""

    owner = User(email="approval-owner@example.com", password_hash="hash")
    session.add(owner)
    session.flush()
    file_resource = FileResource(
        owner_id=owner.id,
        storage_provider="local",
        bucket="local",
        object_key="approval/report.pdf",
        original_filename="report.pdf",
        content_type="application/pdf",
        size_bytes=1,
        sha256="a" * 64,
        status=FileStatus.READY.value,
    )
    knowledge_base = KnowledgeBase(owner_id=owner.id, name="Approval base")
    session.add_all((file_resource, knowledge_base))
    session.flush()
    document = KnowledgeDocument(
        knowledge_base_id=knowledge_base.id, file_id=file_resource.id
    )
    session.add(document)
    session.flush()
    version = DocumentVersion(
        document_id=document.id,
        version_number=1,
        processing_fingerprint="f" * 64,
        parser_name="plain_text",
        parser_version="1",
        chunker_name="structure_aware",
        chunker_config={"max_tokens": 100},
        embedding_profile="test",
        embedding_dimension=3,
    )
    session.add(version)
    session.commit()

    definition = WorkflowDefinition(
        key="knowledge_revision_approval",
        version=1,
        input_type=dict,
        start_step_id="wait_for_approval",
        steps=(
            WorkflowStepDefinition(
                "wait_for_approval",
                "wait_for_approval",
                dict,
                branch=WorkflowBranchDefinition(
                    "decision",
                    (WorkflowBranchCase("approved", "index_and_activate_version"),),
                ),
            ),
            WorkflowStepDefinition(
                "index_and_activate_version", "index_and_activate_version", dict
            ),
        ),
    )
    nodes = WorkflowNodeRegistry((ApprovalNode(), IndexNode()))
    registry = WorkflowDefinitionRegistry(nodes, (definition,))
    return WorkflowService(session, registry), owner, version


def _submit(session: Session) -> tuple[WorkflowService, User, DocumentVersion, str]:
    """提交一个未来过期的 Revision，并返回其稳定 ID。"""

    service, owner, version = _service(session)
    result = service.submit_revision_for_approval(
        owner_id=owner.id,
        document_id=version.document_id,
        document_version_id=version.id,
        definition_key="knowledge_revision_approval",
        definition_version=1,
        expires_at=datetime.now() + timedelta(hours=1),
    )
    return service, owner, version, result.revision.id


def test_approve_keeps_version_pending_and_creates_next_step_without_attempt(
    session: Session,
) -> None:
    service, owner, version, revision_id = _submit(session)

    result = service.approve_revision(
        owner_id=owner.id, revision_id=revision_id, approver_id=owner.id
    )

    assert result.applied is True
    session.expire_all()
    assert result.revision.status == KnowledgeRevisionStatus.APPROVED.value
    assert result.run.status == WorkflowRunStatus.RUNNING.value
    assert (
        session.get(DocumentVersion, version.id).status
        == DocumentVersionStatus.PENDING.value
    )
    steps = session.scalars(
        select(WorkflowStepRun)
        .where(WorkflowStepRun.workflow_run_id == result.run.id)
        .order_by(WorkflowStepRun.step_index)
    ).all()
    assert [step.status for step in steps] == [
        WorkflowStepRunStatus.SUCCEEDED.value,
        WorkflowStepRunStatus.PENDING.value,
    ]
    assert session.scalars(select(WorkflowAttempt)).all() == []
    assert (
        service.approve_revision(
            owner_id=owner.id, revision_id=revision_id, approver_id=owner.id
        ).applied
        is False
    )


def test_reject_cancels_workflow_but_keeps_indexing_fact_pending(
    session: Session,
) -> None:
    service, owner, version, revision_id = _submit(session)

    result = service.reject_revision(
        owner_id=owner.id, revision_id=revision_id, approver_id=owner.id
    )

    assert result.revision.status == KnowledgeRevisionStatus.REJECTED.value
    assert result.run.status == WorkflowRunStatus.CANCELLED.value
    assert (
        session.get(DocumentVersion, version.id).status
        == DocumentVersionStatus.PENDING.value
    )


def test_reconcile_expiry_lazily_cancels_submitted_revision(session: Session) -> None:
    service, owner, version = _service(session)
    submitted = service.submit_revision_for_approval(
        owner_id=owner.id,
        document_id=version.document_id,
        document_version_id=version.id,
        definition_key="knowledge_revision_approval",
        definition_version=1,
        expires_at=datetime.now() - timedelta(seconds=1),
    )

    result = service.reconcile_expired_revision(
        owner_id=owner.id, revision_id=submitted.revision.id, now=datetime.now()
    )

    assert result.applied is True
    assert result.revision.status == KnowledgeRevisionStatus.EXPIRED.value
    assert result.run.status == WorkflowRunStatus.CANCELLED.value
