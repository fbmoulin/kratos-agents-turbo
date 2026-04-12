"""Task lifecycle service."""

from __future__ import annotations

from typing import Any

from src import db
from src.core import (
    NotFoundError,
    TaskStatus,
    ensure_task_transition,
)


class TaskService:
    """Authoritative lifecycle service for tasks."""

    def create_task(
        self,
        *,
        task_id: str,
        file_name: str,
        task_type: str,
        message: str,
        priority: int,
        requested_agent_id: str | None,
        batch_id: str | None = None,
        execution_mode: str = "document",
        input_metadata: dict[str, Any] | None = None,
        conn: Any | None = None,
    ) -> dict[str, Any]:
        return db.create_task(
            task_id=task_id,
            file_name=file_name,
            task_type=task_type,
            status=TaskStatus.QUEUED.value,
            message=message,
            priority=priority,
            requested_agent_id=requested_agent_id,
            batch_id=batch_id,
            session_id=None,
            execution_mode=execution_mode,
            input_metadata=input_metadata,
            conn=conn,
        )

    def get_task(self, task_id: str) -> dict[str, Any]:
        task = db.get_task(task_id)
        if task is None:
            raise NotFoundError(f"Task '{task_id}' not found")
        return task

    def list_tasks(
        self,
        status: str | None = None,
        *,
        batch_id: str | None = None,
        task_type: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        conn: Any | None = None,
    ) -> list[dict[str, Any]]:
        return db.list_tasks(
            status=status,
            batch_id=batch_id,
            task_type=task_type,
            limit=limit,
            offset=offset,
            conn=conn,
        )

    def list_task_summaries(
        self,
        status: str | None = None,
        *,
        batch_id: str | None = None,
        task_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
        conn: Any | None = None,
    ) -> list[dict[str, Any]]:
        return db.list_task_summaries(
            status=status,
            batch_id=batch_id,
            task_type=task_type,
            limit=limit,
            offset=offset,
            conn=conn,
        )

    def list_events(self, task_id: str) -> list[dict[str, Any]]:
        self.get_task(task_id)
        return db.list_task_logs(task_id)

    def attach_execution_context(
        self,
        task_id: str,
        *,
        agent_id: str,
        session_id: str,
    ) -> dict[str, Any]:
        self.get_task(task_id)
        return db.update_task(
            task_id,
            agent_id=agent_id,
            session_id=session_id,
        )

    def mark_running(
        self,
        task_id: str,
        *,
        agent_id: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        current = self.get_task(task_id)
        ensure_task_transition(current["status"], TaskStatus.RUNNING.value)
        update_fields: dict[str, Any] = {
            "status": TaskStatus.RUNNING.value,
            "started_at": db.utc_now(),
        }
        if agent_id is not None:
            update_fields["agent_id"] = agent_id
        if session_id is not None:
            update_fields["session_id"] = session_id
        return db.update_task(
            task_id,
            **update_fields,
        )

    def mark_completed(
        self,
        task_id: str,
        *,
        result: str,
        output_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        current = self.get_task(task_id)
        ensure_task_transition(current["status"], TaskStatus.COMPLETED.value)
        return db.update_task(
            task_id,
            status=TaskStatus.COMPLETED.value,
            result=result,
            output_metadata=output_metadata or {},
            finished_at=db.utc_now(),
        )

    def mark_failed(
        self,
        task_id: str,
        *,
        error: str,
        output_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        current = self.get_task(task_id)
        ensure_task_transition(current["status"], TaskStatus.FAILED.value)
        return db.update_task(
            task_id,
            status=TaskStatus.FAILED.value,
            error=error,
            output_metadata=output_metadata or current.get("output_metadata") or {},
            finished_at=db.utc_now(),
        )

    def mark_cancelled(self, task_id: str) -> dict[str, Any]:
        current = self.get_task(task_id)
        ensure_task_transition(current["status"], TaskStatus.CANCELLED.value)
        return db.update_task(
            task_id,
            status=TaskStatus.CANCELLED.value,
            cancelled_at=db.utc_now(),
        )
