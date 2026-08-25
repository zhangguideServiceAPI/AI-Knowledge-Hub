from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.workflow import (
    WorkflowAttempt,
    WorkflowRun,
    WorkflowStepRun,
)
from app.workflow.state_machine import (
    WorkflowAttemptStatus,
    WorkflowRunStatus,
    WorkflowStepRunStatus,
)


def _create_owner(session: Session) -> User:
    """创建拥有 WorkflowRun 的测试用户，并取得其数据库主键。"""

    owner = User(email="workflow-owner@example.com", password_hash="hashed-password")
    session.add(owner)
    session.flush()
    return owner


def _build_run(owner_id: int, **overrides: object) -> WorkflowRun:
    """构造一个代表知识修订审批流程的最小 WorkflowRun。"""

    values: dict[str, object] = {
        "owner_id": owner_id,
        "definition_key": "knowledge_revision_approval",
        "definition_version": 1,
        "run_input": {
            "document_id": str(uuid4()),
            "document_version_id": str(uuid4()),
            "approval_mode_snapshot": "require_approval",
        },
    }
    values.update(overrides)
    return WorkflowRun(**values)  # type: ignore[arg-type]


def _build_step(workflow_run_id: str, **overrides: object) -> WorkflowStepRun:
    """构造等待人工审批的第一个 StepRun。"""

    values: dict[str, object] = {
        "workflow_run_id": workflow_run_id,
        "step_id": "wait_for_approval",
        "step_index": 0,
    }
    values.update(overrides)
    return WorkflowStepRun(**values)  # type: ignore[arg-type]


def _build_attempt(workflow_step_run_id: str, **overrides: object) -> WorkflowAttempt:
    """构造一个 StepRun 的第一次实际执行尝试 A1。"""

    values: dict[str, object] = {
        "workflow_step_run_id": workflow_step_run_id,
        "attempt_number": 1,
    }
    values.update(overrides)
    return WorkflowAttempt(**values)  # type: ignore[arg-type]


def test_create_workflow_execution_facts_with_defaults(session: Session) -> None:
    owner = _create_owner(session)
    run = _build_run(owner.id)
    session.add(run)
    session.flush()

    step = _build_step(run.id)
    session.add(step)
    session.flush()

    attempt = _build_attempt(step.id)
    session.add(attempt)
    session.flush()
    session.refresh(run)
    session.refresh(step)
    session.refresh(attempt)

    assert UUID(run.id).version == 4
    assert run.status == WorkflowRunStatus.PENDING.value
    assert run.run_input["approval_mode_snapshot"] == "require_approval"
    assert run.created_at is not None
    assert step.status == WorkflowStepRunStatus.PENDING.value
    assert step.output_payload is None
    assert attempt.status == WorkflowAttemptStatus.RUNNING.value
    assert attempt.started_at is not None
    assert attempt.finished_at is None


@pytest.mark.parametrize(
    ("definition_key", "definition_version", "status"),
    [
        ("", 1, WorkflowRunStatus.PENDING.value),
        ("knowledge_revision_approval", 0, WorkflowRunStatus.PENDING.value),
        ("knowledge_revision_approval", 1, "unknown"),
    ],
)
def test_workflow_run_rejects_invalid_definition_or_status(
    session: Session,
    definition_key: str,
    definition_version: int,
    status: str,
) -> None:
    owner = _create_owner(session)
    session.add(
        _build_run(
            owner.id,
            definition_key=definition_key,
            definition_version=definition_version,
            status=status,
        )
    )

    with pytest.raises(IntegrityError):
        session.flush()


def test_failed_workflow_fact_requires_failure_code(session: Session) -> None:
    owner = _create_owner(session)
    session.add(_build_run(owner.id, status=WorkflowRunStatus.FAILED.value))

    with pytest.raises(IntegrityError):
        session.flush()


def test_workflow_run_requires_existing_owner(session: Session) -> None:
    session.add(_build_run(999_999))

    with pytest.raises(IntegrityError):
        session.flush()


def test_step_run_is_unique_by_definition_step_id_and_order(session: Session) -> None:
    owner = _create_owner(session)
    run = _build_run(owner.id)
    session.add(run)
    session.flush()
    session.add(_build_step(run.id))
    session.flush()
    session.add(_build_step(run.id))

    with pytest.raises(IntegrityError):
        session.flush()


def test_step_run_requires_existing_workflow_run(session: Session) -> None:
    session.add(_build_step(str(uuid4())))

    with pytest.raises(IntegrityError):
        session.flush()


@pytest.mark.parametrize(
    ("step_index", "status"),
    [(-1, WorkflowStepRunStatus.PENDING.value), (0, "unknown")],
)
def test_step_run_rejects_invalid_order_or_status(
    session: Session,
    step_index: int,
    status: str,
) -> None:
    owner = _create_owner(session)
    run = _build_run(owner.id)
    session.add(run)
    session.flush()
    session.add(_build_step(run.id, step_index=step_index, status=status))

    with pytest.raises(IntegrityError):
        session.flush()


def test_failed_step_run_requires_failure_code(session: Session) -> None:
    owner = _create_owner(session)
    run = _build_run(owner.id)
    session.add(run)
    session.flush()
    session.add(_build_step(run.id, status=WorkflowStepRunStatus.FAILED.value))

    with pytest.raises(IntegrityError):
        session.flush()


def test_attempt_number_is_unique_for_one_step_run(session: Session) -> None:
    owner = _create_owner(session)
    run = _build_run(owner.id)
    session.add(run)
    session.flush()
    step = _build_step(run.id)
    session.add(step)
    session.flush()
    session.add(_build_attempt(step.id))
    session.flush()
    session.add(_build_attempt(step.id))

    with pytest.raises(IntegrityError):
        session.flush()


def test_attempt_requires_existing_step_run(session: Session) -> None:
    session.add(_build_attempt(str(uuid4())))

    with pytest.raises(IntegrityError):
        session.flush()


@pytest.mark.parametrize(
    ("attempt_number", "status", "failure_code"),
    [
        (0, WorkflowAttemptStatus.RUNNING.value, None),
        (1, "unknown", None),
        (1, WorkflowAttemptStatus.FAILED.value, None),
    ],
)
def test_attempt_rejects_invalid_number_status_or_failure_code(
    session: Session,
    attempt_number: int,
    status: str,
    failure_code: str | None,
) -> None:
    owner = _create_owner(session)
    run = _build_run(owner.id)
    session.add(run)
    session.flush()
    step = _build_step(run.id)
    session.add(step)
    session.flush()
    session.add(
        _build_attempt(
            step.id,
            attempt_number=attempt_number,
            status=status,
            failure_code=failure_code,
        )
    )

    with pytest.raises(IntegrityError):
        session.flush()
