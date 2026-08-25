import pytest

from app.workflow.state_machine import (
    WorkflowRunEvent,
    WorkflowRunStatus,
    get_next_workflow_run_status,
    is_workflow_run_terminal,
)


@pytest.mark.parametrize(
    ("current_status", "event", "expected_status"),
    [
        ("pending", "start", WorkflowRunStatus.RUNNING),
        ("pending", "cancel", WorkflowRunStatus.CANCELLED),
        ("running", "wait_for_approval", WorkflowRunStatus.WAITING_APPROVAL),
        ("running", "complete", WorkflowRunStatus.SUCCEEDED),
        ("running", "fail", WorkflowRunStatus.FAILED),
        ("waiting_approval", "approve", WorkflowRunStatus.RUNNING),
        ("waiting_approval", "reject", WorkflowRunStatus.CANCELLED),
        ("waiting_approval", "expire", WorkflowRunStatus.CANCELLED),
        ("waiting_approval", "cancel", WorkflowRunStatus.CANCELLED),
        ("failed", "resume", WorkflowRunStatus.RUNNING),
    ],
)
def test_get_next_workflow_run_status_returns_only_legal_transition(
    current_status: str,
    event: str,
    expected_status: WorkflowRunStatus,
) -> None:
    assert get_next_workflow_run_status(current_status, event) == expected_status


@pytest.mark.parametrize(
    ("current_status", "event"),
    [
        ("succeeded", WorkflowRunEvent.RESUME),
        ("cancelled", WorkflowRunEvent.START),
        ("waiting_approval", WorkflowRunEvent.COMPLETE),
        ("running", WorkflowRunEvent.CANCEL),
        ("unknown", WorkflowRunEvent.START),
        (WorkflowRunStatus.PENDING, "unknown"),
    ],
)
def test_get_next_workflow_run_status_rejects_illegal_or_unknown_transition(
    current_status: WorkflowRunStatus | str,
    event: WorkflowRunEvent | str,
) -> None:
    with pytest.raises(ValueError):
        get_next_workflow_run_status(current_status, event)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (WorkflowRunStatus.PENDING, False),
        (WorkflowRunStatus.RUNNING, False),
        (WorkflowRunStatus.WAITING_APPROVAL, False),
        (WorkflowRunStatus.FAILED, False),
        (WorkflowRunStatus.SUCCEEDED, True),
        (WorkflowRunStatus.CANCELLED, True),
    ],
)
def test_is_workflow_run_terminal_marks_only_non_resumable_terminal_states(
    status: WorkflowRunStatus,
    expected: bool,
) -> None:
    assert is_workflow_run_terminal(status) is expected
