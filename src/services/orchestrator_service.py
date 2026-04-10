"""Execution orchestration service."""

from __future__ import annotations

from typing import Any

from src import db
from src.agent import AgentRegistry
from src.core import (
    SessionStatus,
    TaskStatus,
    TERMINAL_TASK_STATUSES,
    ValidationError,
    get_logger,
)
from src.events import EventStore, EventType
from src.services.router_service import RouterService
from src.services.session_service import SessionService


class OrchestratorService:
    """Coordinate agent execution, session lifecycle and event persistence."""

    def __init__(
        self,
        *,
        registry: AgentRegistry,
        router_service: RouterService,
        session_service: SessionService,
        event_store: EventStore,
    ) -> None:
        self.registry = registry
        self.router_service = router_service
        self.session_service = session_service
        self.event_store = event_store
        self.logger = get_logger(__name__)

    def execute(
        self,
        *,
        task_id: str,
        file_bytes: bytes,
        file_name: str,
        message: str,
        task_type: str,
        priority: int,
        requested_agent_id: str | None,
        requested_session_id: str | None,
        content_type: str,
    ) -> dict[str, Any]:
        task_record = db.get_task(task_id)
        if task_record is None:
            raise ValidationError(f"Task '{task_id}' does not exist")
        if task_record["status"] in {status.value for status in TERMINAL_TASK_STATUSES}:
            return task_record

        agent_id = self.router_service.resolve_agent_id(
            requested_agent_id=requested_agent_id,
            task_type=task_type,
        )
        agent_definition = self.registry.get(agent_id)
        execution_mode = agent_definition.config.get("execution_mode", "document")
        session = self.session_service.create_or_load_session(
            task_id=task_id,
            agent_id=agent_id,
            requested_session_id=requested_session_id,
            execution_mode=execution_mode,
            metadata={"content_type": content_type, "file_name": file_name},
        )
        session_id = session["id"]
        extra = {"task_id": task_id, "session_id": session_id}

        db.update_task(
            task_id,
            status=TaskStatus.RUNNING.value,
            agent_id=agent_id,
            session_id=session_id,
            started_at=db.utc_now(),
        )
        self.session_service.mark_running(
            session_id,
            current_step="execution_started",
            progress=5,
        )
        self.event_store.append(
            task_id=task_id,
            session_id=session_id,
            event_type=EventType.TASK_STARTED,
            status=TaskStatus.RUNNING.value,
            message="Task execution started",
            payload={"agent_id": agent_id, "priority": priority},
        )
        self.logger.info("task execution started", extra=extra)

        completed_steps = 0
        total_steps = 3

        def emit_step(step_name: str, tool_name: str, payload: dict[str, object]) -> None:
            nonlocal completed_steps
            completed_steps += 1
            progress = min(95, int((completed_steps / total_steps) * 100))
            self.session_service.update_progress(
                session_id,
                current_step=step_name,
                progress=progress,
            )
            self.event_store.append(
                task_id=task_id,
                session_id=session_id,
                event_type=EventType.TOOL_CALLED,
                status=SessionStatus.RUNNING.value,
                step=step_name,
                message=f"Tool invoked: {tool_name}",
                payload={"tool_name": tool_name, **payload},
            )
            self.event_store.append(
                task_id=task_id,
                session_id=session_id,
                event_type=EventType.STEP_EXECUTED,
                status=SessionStatus.RUNNING.value,
                step=step_name,
                message=f"Step completed: {step_name}",
                payload=payload,
            )

        try:
            agent = self.registry.build(agent_id)
            agent_result = agent.run(
                file_bytes=file_bytes,
                message=message,
                task_type=task_type,
                emit_step=emit_step,
            )
            db.update_task(
                task_id,
                status=TaskStatus.COMPLETED.value,
                result=agent_result.result_text,
                output_metadata=agent_result.metadata,
                finished_at=db.utc_now(),
            )
            self.session_service.mark_completed(
                session_id,
                metadata=agent_result.metadata,
            )
            self.event_store.append(
                task_id=task_id,
                session_id=session_id,
                event_type=EventType.TASK_COMPLETED,
                status=TaskStatus.COMPLETED.value,
                message="Task execution completed",
                payload=agent_result.metadata,
            )
            self.logger.info("task execution completed", extra=extra)
            return {
                "task_id": task_id,
                "session_id": session_id,
                "agent_id": agent_id,
                "status": TaskStatus.COMPLETED.value,
                "result": agent_result.result_text,
                "metadata": agent_result.metadata,
            }
        except Exception as exc:
            db.update_task(
                task_id,
                status=TaskStatus.FAILED.value,
                error=str(exc),
                finished_at=db.utc_now(),
            )
            self.session_service.mark_failed(
                session_id,
                error_message=str(exc),
                metadata={"agent_id": agent_id},
            )
            self.event_store.append(
                task_id=task_id,
                session_id=session_id,
                event_type=EventType.TASK_FAILED,
                status=TaskStatus.FAILED.value,
                message="Task execution failed",
                payload={"error": str(exc), "agent_id": agent_id},
            )
            self.logger.exception("task execution failed", extra=extra)
            raise
