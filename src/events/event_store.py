"""Append-only event persistence for task execution."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from src import db


class EventType(StrEnum):
    TASK_CREATED = "TASK_CREATED"
    TASK_DISPATCHED = "TASK_DISPATCHED"
    TASK_DISPATCH_FAILED = "TASK_DISPATCH_FAILED"
    TASK_STARTED = "TASK_STARTED"
    TASK_RETRY_SCHEDULED = "TASK_RETRY_SCHEDULED"
    STEP_EXECUTED = "STEP_EXECUTED"
    TOOL_CALLED = "TOOL_CALLED"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_FAILED = "TASK_FAILED"
    TASK_CANCELLED = "TASK_CANCELLED"


class EventStore:
    """Persist execution events into the task log table."""

    def append(
        self,
        *,
        task_id: str,
        session_id: str | None,
        event_type: EventType,
        status: str | None = None,
        step: str | None = None,
        message: str | None = None,
        payload: dict[str, Any] | None = None,
        conn: Any | None = None,
    ) -> dict[str, Any]:
        return db.insert_task_log(
            task_id=task_id,
            session_id=session_id,
            event_type=event_type.value,
            status=status,
            step=step,
            message=message,
            payload=payload,
            conn=conn,
        )
