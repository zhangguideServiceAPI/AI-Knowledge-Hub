"""Workflow HTTP 资源接口；只做协议转换与认证身份注入。"""

from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_current_user, get_workflow_service
from app.models.knowledge_revision import KnowledgeRevision
from app.models.workflow import WorkflowRun
from app.schemas.user import UserResponse
from app.schemas.workflow import (
    KnowledgeRevisionResponse,
    WorkflowRevisionSubmissionResponse,
    WorkflowRevisionSubmitRequest,
    WorkflowRunResponse,
)
from app.services.workflow_service import WorkflowService

router = APIRouter(prefix="/workflows", tags=["Workflows"])

_APPROVAL_TTL = timedelta(days=7)


def _run_response(run: WorkflowRun) -> WorkflowRunResponse:
    """把 ORM Run 转成安全 HTTP 摘要，不暴露 run_input 或内部输出。"""

    return WorkflowRunResponse(
        id=run.id,
        definition_key=run.definition_key,
        definition_version=run.definition_version,
        status=run.status,
        failure_code=run.failure_code,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


def _revision_response(revision: KnowledgeRevision) -> KnowledgeRevisionResponse:
    """把 ORM Revision 转成业务审批摘要，不返回 Document 内容或审批内部输入。"""

    return KnowledgeRevisionResponse(
        id=revision.id,
        document_id=revision.document_id,
        document_version_id=revision.document_version_id,
        workflow_run_id=revision.workflow_run_id,
        status=revision.status,
        expires_at=revision.expires_at,
        decided_by=revision.decided_by,
        decided_at=revision.decided_at,
    )


@router.post(
    "/knowledge-revisions",
    response_model=WorkflowRevisionSubmissionResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_knowledge_revision(
    request: WorkflowRevisionSubmitRequest,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    workflow_service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> WorkflowRevisionSubmissionResponse:
    """为当前用户的 pending Version 创建需要人工审批的 Workflow。"""

    result = workflow_service.submit_revision_for_approval(
        owner_id=current_user.id,
        document_id=str(request.document_id),
        document_version_id=str(request.document_version_id),
        definition_key="knowledge_revision_approval",
        definition_version=1,
        expires_at=datetime.now() + _APPROVAL_TTL,
    )
    return WorkflowRevisionSubmissionResponse(
        revision=_revision_response(result.revision), run=_run_response(result.run)
    )


@router.get("/runs/{run_id}", response_model=WorkflowRunResponse)
def get_workflow_run(
    run_id: str,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    workflow_service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> WorkflowRunResponse:
    """读取当前用户的 WorkflowRun；越权资源由 Service 统一隐藏为 404。"""

    return _run_response(
        workflow_service.get_run(owner_id=current_user.id, run_id=run_id)
    )


@router.post("/runs/{run_id}/resume", response_model=WorkflowRunResponse)
def resume_workflow_run(
    run_id: str,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    workflow_service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> WorkflowRunResponse:
    """请求恢复可重试失败 Run；Service 决定是否实际从失败 Step 继续。"""

    result = workflow_service.resume_failed_run(owner_id=current_user.id, run_id=run_id)
    return _run_response(result.run)


@router.post(
    "/revisions/{revision_id}/approve",
    response_model=WorkflowRevisionSubmissionResponse,
)
def approve_knowledge_revision(
    revision_id: str,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    workflow_service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> WorkflowRevisionSubmissionResponse:
    """由当前受权所有者批准 Revision；Router 不接收伪造 approver_id。"""

    result = workflow_service.approve_revision(
        owner_id=current_user.id, revision_id=revision_id, approver_id=current_user.id
    )
    return WorkflowRevisionSubmissionResponse(
        revision=_revision_response(result.revision), run=_run_response(result.run)
    )


@router.post(
    "/revisions/{revision_id}/reject", response_model=WorkflowRevisionSubmissionResponse
)
def reject_knowledge_revision(
    revision_id: str,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    workflow_service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> WorkflowRevisionSubmissionResponse:
    """由当前受权所有者拒绝 Revision；拒绝终结审批而不写索引技术失败。"""

    result = workflow_service.reject_revision(
        owner_id=current_user.id, revision_id=revision_id, approver_id=current_user.id
    )
    return WorkflowRevisionSubmissionResponse(
        revision=_revision_response(result.revision), run=_run_response(result.run)
    )
