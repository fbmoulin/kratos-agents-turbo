"""Session lifecycle service."""

from __future__ import annotations

from typing import Any

from src.core import ValidationError
from src.session import SessionManager


class SessionService:
    """Coordinate session lifecycle transitions."""

    def __init__(self, session_manager: SessionManager) -> None:
        self.session_manager = session_manager

    def create_or_load_session(
        self,
        *,
        task_id: str,
        agent_id: str,
        requested_session_id: str | None,
        execution_mode: str = "document",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if requested_session_id:
            session = self.session_manager.load_session(requested_session_id)
            if session["task_id"] != task_id:
                raise ValidationError(
                    "session_id does not belong to the current task and cannot be rebound"
                )
            if session["agent_id"] != agent_id:
                raise ValidationError(
                    "session_id belongs to a different agent and cannot be rebound"
                )
            return session
        return self.session_manager.create_session(
            task_id=task_id,
            agent_id=agent_id,
            execution_mode=execution_mode,
            metadata=metadata,
        )

    def mark_running(
        self,
        session_id: str,
        *,
        current_step: str,
        progress: int,
    ) -> dict[str, Any]:
        return self.session_manager.update_session(
            session_id,
            status="running",
            current_step=current_step,
            progress=progress,
        )

    def update_progress(
        self,
        session_id: str,
        *,
        current_step: str,
        progress: int,
    ) -> dict[str, Any]:
        return self.session_manager.update_session(
            session_id,
            current_step=current_step,
            progress=progress,
        )

    def mark_completed(
        self,
        session_id: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.session_manager.mark_completed(session_id, metadata=metadata)

    def mark_failed(
        self,
        session_id: str,
        *,
        error_message: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.session_manager.mark_failed(
            session_id,
            error_message=error_message,
            metadata=metadata,
        )

    def mark_cancelled(
        self,
        session_id: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.session_manager.mark_cancelled(session_id, metadata=metadata)

    def get_session(self, session_id: str) -> dict[str, Any]:
        return self.session_manager.load_session(session_id)
