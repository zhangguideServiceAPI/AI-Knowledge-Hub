"""WorkflowRun 的纯领域状态机。

这里不访问数据库：后续 WorkflowService 会将本模块返回的目标状态放进带旧状态条件的
UPDATE，以便 MySQL 在多进程并发下完成真正的状态认领。
"""

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType


class WorkflowRunStatus(StrEnum):
    """整条 WorkflowRun 的受控生命周期状态。"""

    PENDING = "pending"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowStepRunStatus(StrEnum):
    """一个 Definition Step 在某条 Run 中的总体状态。"""

    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowAttemptStatus(StrEnum):
    """一次实际执行尝试的受控生命周期状态。"""

    RUNNING = "running"
    WAITING = "waiting"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowRunEvent(StrEnum):
    """会要求整体 WorkflowRun 状态前进的领域事件。"""

    START = "start"
    WAIT_FOR_APPROVAL = "wait_for_approval"
    APPROVE = "approve"
    REJECT = "reject"
    EXPIRE = "expire"
    COMPLETE = "complete"
    FAIL = "fail"
    RESUME = "resume"
    CANCEL = "cancel"


# MappingProxyType 让这张规则表在运行时只读，避免某个调用方意外追加一条未经设计的分支。
WORKFLOW_RUN_TRANSITIONS: Mapping[
    tuple[WorkflowRunStatus, WorkflowRunEvent], WorkflowRunStatus
] = MappingProxyType(
    {
        (WorkflowRunStatus.PENDING, WorkflowRunEvent.START): WorkflowRunStatus.RUNNING,
        (
            WorkflowRunStatus.PENDING,
            WorkflowRunEvent.CANCEL,
        ): WorkflowRunStatus.CANCELLED,
        (
            WorkflowRunStatus.RUNNING,
            WorkflowRunEvent.WAIT_FOR_APPROVAL,
        ): WorkflowRunStatus.WAITING_APPROVAL,
        (
            WorkflowRunStatus.RUNNING,
            WorkflowRunEvent.COMPLETE,
        ): WorkflowRunStatus.SUCCEEDED,
        (WorkflowRunStatus.RUNNING, WorkflowRunEvent.FAIL): WorkflowRunStatus.FAILED,
        (
            WorkflowRunStatus.WAITING_APPROVAL,
            WorkflowRunEvent.APPROVE,
        ): WorkflowRunStatus.RUNNING,
        (
            WorkflowRunStatus.WAITING_APPROVAL,
            WorkflowRunEvent.REJECT,
        ): WorkflowRunStatus.CANCELLED,
        (
            WorkflowRunStatus.WAITING_APPROVAL,
            WorkflowRunEvent.EXPIRE,
        ): WorkflowRunStatus.CANCELLED,
        (
            WorkflowRunStatus.WAITING_APPROVAL,
            WorkflowRunEvent.CANCEL,
        ): WorkflowRunStatus.CANCELLED,
        (WorkflowRunStatus.FAILED, WorkflowRunEvent.RESUME): WorkflowRunStatus.RUNNING,
    }
)

WORKFLOW_RUN_TERMINAL_STATUSES = frozenset(
    {
        WorkflowRunStatus.SUCCEEDED,
        WorkflowRunStatus.CANCELLED,
    }
)


def get_next_workflow_run_status(
    current_status: WorkflowRunStatus | str,
    event: WorkflowRunEvent | str,
) -> WorkflowRunStatus:
    """返回合法事件后的目标状态；未知或非法迁移会抛出 ValueError。"""

    try:
        normalized_status = WorkflowRunStatus(current_status)
        normalized_event = WorkflowRunEvent(event)
    except ValueError as error:
        raise ValueError("未知的 WorkflowRun 状态或事件") from error

    next_status = WORKFLOW_RUN_TRANSITIONS.get((normalized_status, normalized_event))
    if next_status is None:
        raise ValueError(
            "WorkflowRun 不允许从 "
            f"{normalized_status.value} 处理事件 {normalized_event.value}"
        )
    return next_status


def is_workflow_run_terminal(status: WorkflowRunStatus | str) -> bool:
    """判断 Run 是否已到达不能用普通事件继续推进的成功或取消终态。"""

    return WorkflowRunStatus(status) in WORKFLOW_RUN_TERMINAL_STATUSES
