"""Workflow 领域异常到稳定 HTTP 语义的集中映射。"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.schemas.error import ErrorResponse
from app.workflow.exceptions import (
    WorkflowApprovalConflictError,
    WorkflowRetryExhaustedError,
    WorkflowRunNotFoundError,
    WorkflowRunNotRetryableError,
)


async def workflow_not_found_handler(
    _request: Request, _error: WorkflowRunNotFoundError
) -> JSONResponse:
    """将不存在与越权 Run/Revision 统一隐藏为 404。"""

    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=ErrorResponse(detail="Workflow resource not found.").model_dump(),
    )


async def workflow_conflict_handler(
    _request: Request,
    _error: WorkflowApprovalConflictError
    | WorkflowRunNotRetryableError
    | WorkflowRetryExhaustedError,
) -> JSONResponse:
    """将状态竞争、永久失败与重试超限稳定映射为 409。"""

    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content=ErrorResponse(
            detail="Workflow state does not allow this operation."
        ).model_dump(),
    )


def register_workflow_exception_handlers(app: FastAPI) -> None:
    """注册 Workflow 领域异常，确保 Router 不自行构造错误响应。"""

    app.add_exception_handler(WorkflowRunNotFoundError, workflow_not_found_handler)
    app.add_exception_handler(WorkflowApprovalConflictError, workflow_conflict_handler)
    app.add_exception_handler(WorkflowRunNotRetryableError, workflow_conflict_handler)
    app.add_exception_handler(WorkflowRetryExhaustedError, workflow_conflict_handler)
