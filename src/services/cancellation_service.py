"""Cancellation orchestration for task and batch runtime flows."""

from __future__ import annotations

from celery.result import AsyncResult

from src.core import InvalidStateTransition, TaskStatus, get_logger
from src.events import EventStore, EventType
from src.services.batch_service import BatchService
from src.services.session_service import SessionService
from src.services.task_service import TaskService
from src.worker.celery_app import celery_app


class CancellationService:
    """Coordinate cancellation across task, session and broker layers."""

    def __init__(
        self,
        *,
        task_service: TaskService,
        session_service: SessionService,
        batch_service: BatchService,
        event_store: EventStore,
    ) -> None:
        self.task_service = task_service
        self.session_service = session_service
        self.batch_service = batch_service
        self.event_store = event_store
        self.logger = get_logger(__name__)

    def cancel_task(self, task_id: str) -> dict[str, str]:
        record = self.task_service.get_task(task_id)
        if record["status"] == TaskStatus.CANCELLED.value:
            return {"status": "cancelled"}
        if record["status"] in {TaskStatus.COMPLETED.value, TaskStatus.FAILED.value}:
            raise InvalidStateTransition(
                f"Invalid task transition: {record['status']} -> {TaskStatus.CANCELLED.value}"
            )

        self._cancel_task_record(record)
        return {"status": "cancelled"}

    def cancel_batch(self, batch_id: str) -> dict[str, object]:
        self.batch_service.get_batch(batch_id)
        tasks = self.task_service.list_tasks(batch_id=batch_id)
        cancelled_tasks = 0
        skipped_tasks = 0
        for record in tasks:
            if self._cancel_task_record(record):
                cancelled_tasks += 1
            else:
                skipped_tasks += 1

        summary = self.batch_service.get_batch_with_tasks(batch_id)
        return {
            "batch_id": batch_id,
            "status": summary["status"],
            "cancelled_tasks": cancelled_tasks,
            "skipped_tasks": skipped_tasks,
            "counts": summary["counts"],
        }

    def _cancel_task_record(self, record: dict[str, object]) -> bool:
        task_id = str(record["id"])
        task_status = str(record["status"])
        session_id = record.get("session_id")
        if task_status in {
            TaskStatus.COMPLETED.value,
            TaskStatus.FAILED.value,
            TaskStatus.CANCELLED.value,
        }:
            return False

        self.task_service.mark_cancelled(task_id)
        if session_id:
            try:
                self.session_service.mark_cancelled(
                    str(session_id),
                    metadata={"task_id": task_id},
                )
            except Exception as exc:
                self.logger.exception(
                    "task/session cancel sync failed",
                    extra={"task_id": task_id, "session_id": str(session_id)},
                )
                try:
                    self.session_service.mark_failed(
                        str(session_id),
                        error_message=f"state_sync_error: {exc}",
                        metadata={"state_sync_error": True, "task_id": task_id},
                    )
                except Exception:
                    self.logger.exception(
                        "failed to recover session during cancel",
                        extra={"task_id": task_id, "session_id": str(session_id)},
                    )
                self.event_store.append(
                    task_id=task_id,
                    session_id=str(session_id),
                    event_type=EventType.TASK_FAILED,
                    status="failed",
                    message="Task/session cancel sync failed",
                    payload={
                        "error": f"state_sync_error: {exc}",
                        "state_sync_error": True,
                    },
                )
                raise

        self.event_store.append(
            task_id=task_id,
            session_id=str(session_id) if session_id else None,
            event_type=EventType.TASK_CANCELLED,
            status="cancelled",
            message="Task cancelled by API request",
            payload={"celery_task_id": task_id},
        )
        AsyncResult(task_id, app=celery_app).revoke(terminate=True)
        self.logger.info(
            "task cancelled",
            extra={
                "task_id": task_id,
                "session_id": str(session_id) if session_id else "-",
                "batch_id": str(record.get("batch_id") or "-"),
            },
        )
        return True
