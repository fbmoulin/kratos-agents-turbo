"""FastAPI application for the legal agent execution platform."""

from __future__ import annotations

import base64
import uuid
from typing import Annotated

from celery.result import AsyncResult
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse

from src import db
from src.core import (
    ApplicationError,
    InvalidStateTransition,
    NotFoundError,
    PersistenceError,
    TaskStatus,
    ValidationError,
    configure_logging,
    ensure_task_transition,
    get_logger,
    get_settings,
)
from src.events import EventType
from src.services import create_platform_services
from src.worker.celery_app import celery_app
from src.worker.tasks import process_document_task

settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger(__name__)
services = create_platform_services()

app = FastAPI(
    title="Kratos Agents Turbo API",
    version=settings.service_version,
)


@app.exception_handler(ValidationError)
async def handle_validation_error(_, exc: ValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(NotFoundError)
async def handle_not_found(_, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(InvalidStateTransition)
async def handle_state_error(_, exc: InvalidStateTransition) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(PersistenceError)
async def handle_persistence_error(_, exc: PersistenceError) -> JSONResponse:
    logger.exception("persistence error", extra={"task_id": "-", "session_id": "-"})
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(ApplicationError)
async def handle_application_error(_, exc: ApplicationError) -> JSONResponse:
    logger.exception("application error", extra={"task_id": "-", "session_id": "-"})
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/health")
async def health() -> dict[str, str]:
    return settings.health_payload()


@app.post("/tasks")
async def submit_task(
    file: Annotated[UploadFile, File(...)],
    message: Annotated[str | None, Form()] = None,
    tipo: Annotated[str | None, Form()] = None,
    task_type: Annotated[str | None, Form()] = None,
    priority: Annotated[int | None, Form()] = 0,
    agent_id: Annotated[str | None, Form()] = None,
    session_id: Annotated[str | None, Form()] = None,
) -> dict[str, object]:
    file_bytes = await file.read()
    validated = services.validator_service.validate_submission(
        file_bytes=file_bytes,
        file_name=file.filename,
        content_type=file.content_type,
        message=message,
        task_type=task_type or tipo,
        priority=priority,
        requested_agent_id=agent_id,
        requested_session_id=session_id,
    )
    task_id = str(uuid.uuid4())

    db.create_task(
        task_id=task_id,
        file_name=validated.file_name,
        task_type=validated.task_type,
        status=TaskStatus.QUEUED.value,
        message=validated.message,
        priority=validated.priority,
        requested_agent_id=validated.requested_agent_id,
        session_id=validated.requested_session_id,
        input_metadata={"content_type": validated.content_type},
    )
    services.event_store.append(
        task_id=task_id,
        session_id=validated.requested_session_id,
        event_type=EventType.TASK_CREATED,
        status=TaskStatus.QUEUED.value,
        message="Task registered and queued",
        payload={
            "file_name": validated.file_name,
            "task_type": validated.task_type,
            "priority": validated.priority,
            "requested_agent_id": validated.requested_agent_id,
        },
    )

    encoded_file = base64.b64encode(file_bytes).decode("utf-8")
    process_document_task.apply_async(
        kwargs={
            "task_id": task_id,
            "file_content_b64": encoded_file,
            "file_name": validated.file_name,
            "message": validated.message,
            "task_type": validated.task_type,
            "priority": validated.priority,
            "requested_agent_id": validated.requested_agent_id,
            "requested_session_id": validated.requested_session_id,
            "content_type": validated.content_type,
        },
        task_id=task_id,
        queue=settings.celery_task_queue,
    )
    logger.info("task submitted", extra={"task_id": task_id, "session_id": "-"})
    return {
        "task_id": task_id,
        "status": TaskStatus.QUEUED.value,
        "requested_agent_id": validated.requested_agent_id,
    }


@app.get("/tasks/{task_id}")
async def get_task_status(task_id: str) -> dict[str, object]:
    record = db.get_task(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return record


@app.get("/tasks")
async def list_all_tasks(
    status: str | None = Query(default=None),
) -> list[dict[str, object]]:
    return db.list_tasks(status=status)


@app.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str) -> dict[str, str]:
    record = db.get_task(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if record["status"] == TaskStatus.CANCELLED.value:
        return {"status": TaskStatus.CANCELLED.value}

    ensure_task_transition(record["status"], TaskStatus.CANCELLED.value)
    db.update_task(task_id, status=TaskStatus.CANCELLED.value, cancelled_at=db.utc_now())
    if record.get("session_id"):
        services.session_service.mark_cancelled(
            record["session_id"],
            metadata={"task_id": task_id},
        )
    services.event_store.append(
        task_id=task_id,
        session_id=record.get("session_id"),
        event_type=EventType.TASK_CANCELLED,
        status=TaskStatus.CANCELLED.value,
        message="Task cancelled by API request",
        payload={"celery_task_id": task_id},
    )
    AsyncResult(task_id, app=celery_app).revoke(terminate=True)
    logger.info(
        "task cancelled",
        extra={"task_id": task_id, "session_id": record.get("session_id", "-")},
    )
    return {"status": TaskStatus.CANCELLED.value}
