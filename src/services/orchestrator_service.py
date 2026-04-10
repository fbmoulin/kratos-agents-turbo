"""Execution orchestration service."""

from __future__ import annotations

from typing import Any

from src.agent import AgentRegistry
from src.core import (
    SessionStatus,
    get_logger,
)
from src.events import EventStore, EventType
from src.services.router_service import RouterService
from src.services.session_service import SessionService
from src.services.task_service import TaskService


class OrchestratorService:
    """Coordinate agent execution, session lifecycle and event persistence."""

    def __init__(
        self,
        *,
        registry: AgentRegistry,
        task_service: TaskService,
        router_service: RouterService,
        session_service: SessionService,
        event_store: EventStore,
    ) -> None:
        self.registry = registry
        self.task_service = task_service
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
        task_record = self.task_service.get_task(task_id)
        if task_record["status"] in {
            "completed",
            "failed",
            "cancelled",
        }:
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

        self.task_service.mark_running(
            task_id,
            agent_id=agent_id,
            session_id=session_id,
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
            status="running",
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
            task_state = self.task_service.mark_completed(
                task_id,
                result=agent_result.result_text,
                output_metadata=agent_result.metadata,
            )
            try:
                self.session_service.mark_completed(
                    session_id,
                    metadata=agent_result.metadata,
                )
            except Exception as sync_exc:
                self._handle_state_sync_error(
                    task_id=task_id,
                    session_id=session_id,
                    agent_id=agent_id,
                    error=sync_exc,
                    extra=extra,
                )
                raise
            self.event_store.append(
                task_id=task_id,
                session_id=session_id,
                event_type=EventType.TASK_COMPLETED,
                status=task_state["status"],
                message="Task execution completed",
                payload={"agent_id": agent_id, **agent_result.metadata},
            )
            self.logger.info("task execution completed", extra=extra)
            return {
                "task_id": task_id,
                "session_id": session_id,
                "agent_id": agent_id,
                "status": task_state["status"],
                "result": agent_result.result_text,
                "metadata": agent_result.metadata,
            }
        except Exception as exc:
            try:
                self.task_service.mark_failed(
                    task_id,
                    error=str(exc),
                    output_metadata={"agent_id": agent_id},
                )
                self.session_service.mark_failed(
                    session_id,
                    error_message=str(exc),
                    metadata={"agent_id": agent_id},
                )
            except Exception as sync_exc:
                self._handle_state_sync_error(
                    task_id=task_id,
                    session_id=session_id,
                    agent_id=agent_id,
                    error=sync_exc,
                    extra=extra,
                )
            self.event_store.append(
                task_id=task_id,
                session_id=session_id,
                event_type=EventType.TASK_FAILED,
                status="failed",
                message="Task execution failed",
                payload={"error": str(exc), "agent_id": agent_id},
            )
            self.logger.exception("task execution failed", extra=extra)
            raise

    def _handle_state_sync_error(
        self,
        *,
        task_id: str,
        session_id: str,
        agent_id: str,
        error: Exception,
        extra: dict[str, str],
    ) -> None:
        error_message = f"state_sync_error: {error}"
        self.logger.exception("state sync failed", extra=extra)
        try:
            task = self.task_service.get_task(task_id)
            if task["status"] not in {"completed", "failed", "cancelled"}:
                self.task_service.mark_failed(
                    task_id,
                    error=error_message,
                    output_metadata={
                        "agent_id": agent_id,
                        "state_sync_error": True,
                    },
                )
        except Exception:
            self.logger.exception("failed to recover task state", extra=extra)
        try:
            session = self.session_service.get_session(session_id)
            if session["status"] not in {"completed", "failed", "cancelled"}:
                self.session_service.mark_failed(
                    session_id,
                    error_message=error_message,
                    metadata={
                        "agent_id": agent_id,
                        "state_sync_error": True,
                    },
                )
        except Exception:
            self.logger.exception("failed to recover session state", extra=extra)
        try:
            self.event_store.append(
                task_id=task_id,
                session_id=session_id,
                event_type=EventType.TASK_FAILED,
                status="failed",
                message="Task/session state sync failed",
                payload={
                    "agent_id": agent_id,
                    "error": error_message,
                    "state_sync_error": True,
                },
            )
        except Exception:
            self.logger.exception("failed to persist state sync event", extra=extra)
