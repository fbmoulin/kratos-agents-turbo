"""Session persistence and lifecycle management."""

from __future__ import annotations

import uuid
from typing import Any

from psycopg.errors import UniqueViolation

from src import db
from src.core import (
    NotFoundError,
    SessionStatus,
    ensure_session_transition,
)


class SessionManager:
    """Manage session creation and state transitions."""

    def create_session(
        self,
        *,
        task_id: str,
        agent_id: str,
        execution_mode: str = "document",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session_id = str(uuid.uuid4())
        try:
            return db.create_session(
                session_id=session_id,
                task_id=task_id,
                agent_id=agent_id,
                status=SessionStatus.QUEUED.value,
                execution_mode=execution_mode,
                metadata=metadata,
            )
        except UniqueViolation:
            session = self.load_session_by_task(task_id)
            if session is None:
                raise
            return session

    def load_session(self, session_id: str) -> dict[str, Any]:
        session = db.get_session(session_id)
        if session is None:
            raise NotFoundError(f"Session '{session_id}' not found")
        return session

    def load_session_by_task(self, task_id: str) -> dict[str, Any] | None:
        return db.get_session_by_task_id(task_id)

    def update_session(self, session_id: str, **fields: Any) -> dict[str, Any]:
        if "status" in fields:
            current = self.load_session(session_id)
            ensure_session_transition(current["status"], fields["status"])
        return db.update_session(session_id, **fields)

    def mark_completed(
        self,
        session_id: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.update_session(
            session_id,
            status=SessionStatus.COMPLETED.value,
            current_step="completed",
            progress=100,
            metadata=metadata or {},
        )

    def mark_failed(
        self,
        session_id: str,
        *,
        error_message: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        merged_metadata = dict(metadata or {})
        merged_metadata["error"] = error_message
        return self.update_session(
            session_id,
            status=SessionStatus.FAILED.value,
            current_step="failed",
            metadata=merged_metadata,
        )

    def mark_cancelled(
        self,
        session_id: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.update_session(
            session_id,
            status=SessionStatus.CANCELLED.value,
            current_step="cancelled",
            metadata=metadata or {},
        )
