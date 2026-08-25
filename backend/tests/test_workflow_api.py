"""Story 6.7 Workflow Router 的认证身份转交与资源隐藏测试。"""

from datetime import datetime
from unittest.mock import Mock
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user, get_workflow_service
from app.main import app
from app.models.workflow import WorkflowRun
from app.schemas.user import UserResponse
from app.services.workflow_service import WorkflowService
from app.workflow.exceptions import WorkflowRunNotFoundError
from app.workflow.state_machine import WorkflowRunStatus


def _current_user() -> UserResponse:
    """构造 API 测试使用的已认证用户，不依赖 JWT 细节。"""

    now = datetime.now()
    return UserResponse(
        id=11,
        email="workflow-api@example.com",
        nickname=None,
        avatar_url=None,
        status="active",
        created_at=now,
        updated_at=now,
    )


def _run() -> WorkflowRun:
    """构造已持久化形态的 Run 摘要，供 Router 验证响应转换。"""

    now = datetime.now()
    return WorkflowRun(
        id=str(uuid4()),
        owner_id=11,
        definition_key="knowledge_revision_approval",
        definition_version=1,
        run_input={},
        status=WorkflowRunStatus.WAITING_APPROVAL.value,
        created_at=now,
        updated_at=now,
    )


def test_get_workflow_run_passes_authenticated_owner_to_service() -> None:
    workflow_service = Mock(spec=WorkflowService)
    run = _run()
    workflow_service.get_run.return_value = run
    app.dependency_overrides[get_current_user] = _current_user
    app.dependency_overrides[get_workflow_service] = lambda: workflow_service

    try:
        with TestClient(app) as client:
            response = client.get(f"/workflows/runs/{run.id}")
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_workflow_service, None)

    assert response.status_code == 200
    assert response.json()["id"] == run.id
    workflow_service.get_run.assert_called_once_with(owner_id=11, run_id=run.id)


def test_workflow_not_found_is_hidden_as_404() -> None:
    workflow_service = Mock(spec=WorkflowService)
    workflow_service.get_run.side_effect = WorkflowRunNotFoundError()
    app.dependency_overrides[get_current_user] = _current_user
    app.dependency_overrides[get_workflow_service] = lambda: workflow_service

    try:
        with TestClient(app) as client:
            response = client.get(f"/workflows/runs/{uuid4()}")
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_workflow_service, None)

    assert response.status_code == 404
    assert response.json() == {"detail": "Workflow resource not found."}
