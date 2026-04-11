"""Celery tasks for legal agent execution."""

from __future__ import annotations

from celery import Task
from celery.exceptions import Ignore

from src import db
from src.core import (
    TaskStatus,
    compute_retry_delay,
    configure_logging,
    get_logger,
    get_settings,
    is_retryable_exception,
)
from src.events import EventType
from src.services import create_platform_services
from src.worker.celery_app import celery_app

services = create_platform_services()
settings = get_settings()
logger = get_logger(__name__)
configure_logging(settings.log_level)


def _mark_staged_input_cleaned(task_id: str, staged_path: str) -> None:
    record = db.get_task(task_id)
    if record is None:
        return
    input_metadata = dict(record.get("input_metadata") or {})
    if input_metadata.get("staged_path") == staged_path:
        input_metadata.pop("staged_path", None)
    input_metadata["staged_input_deleted"] = True
    input_metadata["staged_input_deleted_at"] = db.utc_now()
    db.update_task(task_id, input_metadata=input_metadata)


class BaseTask(Task):
    """Base task with cancellation checks."""

    abstract = True

    def check_cancelled(self, task_id: str) -> None:
        record = db.get_task(task_id)
        if record and record.get("status") == TaskStatus.CANCELLED.value:
            raise Ignore("Task was cancelled")

    @staticmethod
    def retry_countdown(attempt: int) -> int:
        return compute_retry_delay(
            attempt=attempt,
            base_seconds=settings.celery_retry_backoff_base_seconds,
            max_seconds=settings.celery_retry_backoff_max_seconds,
        )

    @staticmethod
    def max_retries_for_task_type(task_type: str) -> int:
        return settings.max_retries_for_task_type(task_type)

    def schedule_retry(
        self,
        *,
        task_id: str,
        task_type: str,
        reason: Exception,
    ) -> bool:
        attempts = int(self.request.retries or 0) + 1
        max_retries = self.max_retries_for_task_type(task_type)
        if attempts > max_retries:
            return False
        countdown = self.retry_countdown(self.request.retries)
        record = db.get_task(task_id) or {}
        session_id = record.get("session_id")
        services.event_store.append(
            task_id=task_id,
            session_id=str(session_id) if session_id else None,
            event_type=EventType.TASK_RETRY_SCHEDULED,
            status=str(record.get("status") or TaskStatus.QUEUED.value),
            message="Task retry scheduled",
            payload={
                "attempt": attempts,
                "max_retries": max_retries,
                "retry_in_seconds": countdown,
                "error": str(reason),
            },
        )
        logger.warning(
            "task retry scheduled",
            extra={
                "task_id": task_id,
                "session_id": str(session_id) if session_id else "-",
                "batch_id": str(record.get("batch_id") or "-"),
            },
        )
        raise self.retry(exc=reason, countdown=countdown, max_retries=max_retries)

    def mark_terminal_failure(
        self,
        *,
        task_id: str,
        task_type: str,
        error: Exception,
    ) -> None:
        record = db.get_task(task_id)
        if record is None:
            return
        if record["status"] in {
            TaskStatus.COMPLETED.value,
            TaskStatus.FAILED.value,
            TaskStatus.CANCELLED.value,
        }:
            return
        session_id = record.get("session_id")
        services.task_service.mark_failed(
            task_id,
            error=str(error),
            output_metadata={"task_type": task_type},
        )
        if session_id:
            try:
                services.session_service.mark_failed(
                    str(session_id),
                    error_message=str(error),
                    metadata={"task_type": task_type},
                )
            except Exception:
                logger.exception(
                    "failed to mark session as failed after terminal worker error",
                    extra={
                        "task_id": task_id,
                        "session_id": str(session_id),
                        "batch_id": str(record.get("batch_id") or "-"),
                    },
                )
        services.event_store.append(
            task_id=task_id,
            session_id=str(session_id) if session_id else None,
            event_type=EventType.TASK_FAILED,
            status=TaskStatus.FAILED.value,
            message="Task execution failed after terminal worker error",
            payload={"error": str(error), "task_type": task_type},
        )


@celery_app.task(bind=True, base=BaseTask, name="process_document")
def process_document_task(
    self,
    *,
    task_id: str,
    staged_path: str | None = None,
    file_content_b64: str | None = None,
    file_name: str,
    message: str,
    task_type: str,
    priority: int,
    requested_agent_id: str | None = None,
    requested_session_id: str | None = None,
    content_type: str = "application/pdf",
    batch_id: str | None = None,
) -> dict[str, object]:
    cleanup_staged_input = False
    try:
        self.check_cancelled(task_id)
        if staged_path:
            file_bytes = services.staging_service.load_staged_input(staged_path)
        elif file_content_b64:
            import base64

            file_bytes = base64.b64decode(file_content_b64.encode("utf-8"))
        else:
            raise ValueError("Either staged_path or file_content_b64 must be provided")

        logger.info(
            "worker task received",
            extra={"task_id": task_id, "session_id": "-", "batch_id": batch_id or "-"},
        )
        result = services.orchestrator_service.execute(
            task_id=task_id,
            file_bytes=file_bytes,
            file_name=file_name,
            message=message,
            task_type=task_type,
            priority=priority,
            requested_agent_id=requested_agent_id,
            requested_session_id=requested_session_id,
            content_type=content_type,
        )
        cleanup_staged_input = True
        return result
    except Ignore:
        cleanup_staged_input = True
        raise
    except Exception as exc:
        if is_retryable_exception(exc):
            if self.schedule_retry(task_id=task_id, task_type=task_type, reason=exc):
                return {}
        self.mark_terminal_failure(task_id=task_id, task_type=task_type, error=exc)
        cleanup_staged_input = True
        raise
    finally:
        if cleanup_staged_input and staged_path:
            try:
                services.staging_service.delete_staged_input(staged_path)
                _mark_staged_input_cleaned(task_id, staged_path)
            except Exception:
                logger.exception(
                    "failed to cleanup staged input",
                    extra={
                        "task_id": task_id,
                        "session_id": "-",
                        "batch_id": batch_id or "-",
                    },
                )
