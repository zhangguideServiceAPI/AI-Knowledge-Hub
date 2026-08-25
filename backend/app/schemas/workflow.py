"""Workflow HTTP 输入输出 Schema；不承载状态迁移或数据库访问。"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class WorkflowRevisionSubmitRequest(BaseModel):
    """启动知识修订审批时客户端指定的已准备 Document 与 Version。"""

    model_config = ConfigDict(extra="forbid")

    document_id: UUID
    document_version_id: UUID


class WorkflowRunResponse(BaseModel):
    """对当前所有者公开的 WorkflowRun 安全摘要。"""

    id: UUID
    definition_key: str
    definition_version: int
    status: str
    failure_code: str | None
    created_at: datetime
    updated_at: datetime


class KnowledgeRevisionResponse(BaseModel):
    """对当前所有者公开的 Revision 业务审批摘要。"""

    id: UUID
    document_id: UUID
    document_version_id: UUID
    workflow_run_id: UUID
    status: str
    expires_at: datetime
    decided_by: int | None
    decided_at: datetime | None


class WorkflowRevisionSubmissionResponse(BaseModel):
    """提交审批后返回 Revision 和已进入等待状态的 Run。"""

    revision: KnowledgeRevisionResponse
    run: WorkflowRunResponse
