"""Celery tasks for legal agent execution."""

from __future__ import annotations

import base64

from celery import Task
from celery.exceptions import Ignore

from src import db
from src.core import TaskStatus, configure_logging, get_logger, get_settings
from src.services import create_platform_services
from src.worker.celery_app import celery_app

services = create_platform_services()
settings = get_settings()
logger = get_logger(__name__)
configure_logging(settings.log_level)


class BaseTask(Task):
    """Base task with cancellation checks."""

    abstract = True

    def check_cancelled(self, task_id: str) -> None:
        record = db.get_task(task_id)
        if record and record.get("status") == TaskStatus.CANCELLED.value:
            raise Ignore("Task was cancelled")


@celery_app.task(bind=True, base=BaseTask, name="process_document")
def process_document_task(
    self,
    *,
    task_id: str,
    file_content_b64: str,
    file_name: str,
    message: str,
    task_type: str,
    priority: int,
    requested_agent_id: str | None = None,
    requested_session_id: str | None = None,
    content_type: str = "application/pdf",
) -> dict[str, object]:
    self.check_cancelled(task_id)
    file_bytes = base64.b64decode(file_content_b64.encode("utf-8"))
    logger.info("worker task received", extra={"task_id": task_id, "session_id": "-"})
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
    return result
