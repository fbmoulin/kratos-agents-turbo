"""Execution status and transition rules."""

from __future__ import annotations

from enum import StrEnum

from src.core.exceptions import InvalidStateTransition


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SessionStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_TASK_STATUSES = {
    TaskStatus.COMPLETED,
    TaskStatus.FAILED,
    TaskStatus.CANCELLED,
}

TERMINAL_SESSION_STATUSES = {
    SessionStatus.COMPLETED,
    SessionStatus.FAILED,
    SessionStatus.CANCELLED,
}

TASK_TRANSITIONS = {
    TaskStatus.QUEUED: {TaskStatus.RUNNING, TaskStatus.CANCELLED},
    TaskStatus.RUNNING: {
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.COMPLETED: set(),
    TaskStatus.FAILED: set(),
    TaskStatus.CANCELLED: set(),
}

SESSION_TRANSITIONS = {
    SessionStatus.QUEUED: {SessionStatus.RUNNING, SessionStatus.CANCELLED},
    SessionStatus.RUNNING: {
        SessionStatus.COMPLETED,
        SessionStatus.FAILED,
        SessionStatus.CANCELLED,
    },
    SessionStatus.COMPLETED: set(),
    SessionStatus.FAILED: set(),
    SessionStatus.CANCELLED: set(),
}


def ensure_task_transition(current: str, target: str) -> None:
    """Validate a task transition."""

    current_status = TaskStatus(current)
    target_status = TaskStatus(target)
    if current_status == target_status:
        return
    if target_status not in TASK_TRANSITIONS[current_status]:
        raise InvalidStateTransition(
            f"Invalid task transition: {current_status.value} -> {target_status.value}"
        )


def ensure_session_transition(current: str, target: str) -> None:
    """Validate a session transition."""

    current_status = SessionStatus(current)
    target_status = SessionStatus(target)
    if current_status == target_status:
        return
    if target_status not in SESSION_TRANSITIONS[current_status]:
        raise InvalidStateTransition(
            f"Invalid session transition: {current_status.value} -> {target_status.value}"
        )
