"""FastAPI application for the legal agent execution platform."""

from __future__ import annotations

import uuid
from typing import Annotated

from celery.result import AsyncResult
from fastapi import FastAPI, File, Form, Query, UploadFile
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
    get_logger,
    get_settings,
)
from src.events import EventType
from src.services import create_platform_services
from src.worker.celery_app import celery_app

settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger(__name__)
services = create_platform_services()

app = FastAPI(
    title="Kratos Agents Turbo API",
    version=settings.service_version,
)

TERMINAL_TASK_STATUSES = {
    TaskStatus.COMPLETED.value,
    TaskStatus.FAILED.value,
    TaskStatus.CANCELLED.value,
}


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


def _prepare_task_submission(
    *,
    file_bytes: bytes,
    file_name: str | None,
    content_type: str | None,
    message: str | None,
    task_type: str | None,
    priority: int | None,
    agent_id: str | None,
    session_id: str | None,
    batch_id: str | None = None,
    batch_item_index: int | None = None,
    batch_total_tasks: int | None = None,
) -> dict[str, object]:
    validated = services.validator_service.validate_submission(
        file_bytes=file_bytes,
        file_name=file_name,
        content_type=content_type,
        message=message,
        task_type=task_type,
        priority=priority,
        requested_agent_id=agent_id,
        requested_session_id=session_id,
    )
    task_id = str(uuid.uuid4())
    staged = services.staging_service.stage_upload(
        task_id=task_id,
        file_name=validated.file_name,
        file_bytes=file_bytes,
        batch_id=batch_id,
    )
    input_metadata = {
        "content_type": validated.content_type,
        "staged_path": staged["staged_path"],
        "staged_size_bytes": staged["size_bytes"],
    }
    if batch_id:
        input_metadata["batch_item_index"] = batch_item_index
        input_metadata["batch_total_tasks"] = batch_total_tasks
    return {
        "task_id": task_id,
        "file_name": validated.file_name,
        "task_type": validated.task_type,
        "message": validated.message,
        "priority": validated.priority,
        "requested_agent_id": validated.requested_agent_id,
        "requested_session_id": validated.requested_session_id,
        "content_type": validated.content_type,
        "staged_path": staged["staged_path"],
        "input_metadata": input_metadata,
        "queue": settings.queue_for_task_type(validated.task_type),
    }


def _register_and_dispatch_task(
    *,
    file_bytes: bytes,
    file_name: str | None,
    content_type: str | None,
    message: str | None,
    task_type: str | None,
    priority: int | None,
    agent_id: str | None,
    session_id: str | None,
    batch_id: str | None = None,
    batch_item_index: int | None = None,
    batch_total_tasks: int | None = None,
) -> dict[str, object]:
    prepared = _prepare_task_submission(
        file_bytes=file_bytes,
        file_name=file_name,
        content_type=content_type,
        message=message,
        task_type=task_type,
        priority=priority,
        agent_id=agent_id,
        session_id=session_id,
        batch_id=batch_id,
        batch_item_index=batch_item_index,
        batch_total_tasks=batch_total_tasks,
    )

    try:
        with db.transaction() as conn:
            services.task_service.create_task(
                task_id=str(prepared["task_id"]),
                file_name=str(prepared["file_name"]),
                task_type=str(prepared["task_type"]),
                message=str(prepared["message"]),
                priority=int(prepared["priority"]),
                requested_agent_id=prepared["requested_agent_id"],
                batch_id=batch_id,
                input_metadata=dict(prepared["input_metadata"]),
                conn=conn,
            )
            services.event_store.append(
                task_id=str(prepared["task_id"]),
                session_id=None,
                event_type=EventType.TASK_CREATED,
                status="queued",
                message="Task registered and queued",
                payload={
                    "batch_id": batch_id,
                    "batch_item_index": batch_item_index,
                    "file_name": prepared["file_name"],
                    "task_type": prepared["task_type"],
                    "priority": prepared["priority"],
                    "requested_agent_id": prepared["requested_agent_id"],
                },
                conn=conn,
            )
            db.create_task_dispatch(
                task_id=str(prepared["task_id"]),
                queue_name=str(prepared["queue"]),
                payload={
                    "task_id": prepared["task_id"],
                    "staged_path": prepared["staged_path"],
                    "file_name": prepared["file_name"],
                    "message": prepared["message"],
                    "task_type": prepared["task_type"],
                    "priority": prepared["priority"],
                    "requested_agent_id": prepared["requested_agent_id"],
                    "requested_session_id": prepared["requested_session_id"],
                    "content_type": prepared["content_type"],
                    "batch_id": batch_id,
                },
                conn=conn,
            )
    except Exception:
        services.staging_service.delete_staged_input(str(prepared["staged_path"]))
        raise
    services.dispatch_service.dispatch_task(str(prepared["task_id"]))
    logger.info(
        "task submitted",
        extra={
            "task_id": str(prepared["task_id"]),
            "session_id": "-",
            "batch_id": batch_id or "-",
        },
    )
    return {
        "task_id": prepared["task_id"],
        "task_type": prepared["task_type"],
        "priority": prepared["priority"],
        "requested_agent_id": prepared["requested_agent_id"],
        "queue": prepared["queue"],
    }


def _cancel_task_record(record: dict[str, object]) -> bool:
    task_id = str(record["id"])
    task_status = str(record["status"])
    session_id = record.get("session_id")
    if task_status in TERMINAL_TASK_STATUSES:
        return False

    services.task_service.mark_cancelled(task_id)
    if session_id:
        try:
            services.session_service.mark_cancelled(
                str(session_id),
                metadata={"task_id": task_id},
            )
        except Exception as exc:
            logger.exception(
                "task/session cancel sync failed",
                extra={"task_id": task_id, "session_id": str(session_id)},
            )
            try:
                services.session_service.mark_failed(
                    str(session_id),
                    error_message=f"state_sync_error: {exc}",
                    metadata={"state_sync_error": True, "task_id": task_id},
                )
            except Exception:
                logger.exception(
                    "failed to recover session during cancel",
                    extra={"task_id": task_id, "session_id": str(session_id)},
                )
            services.event_store.append(
                task_id=task_id,
                session_id=str(session_id),
                event_type=EventType.TASK_FAILED,
                status="failed",
                message="Task/session cancel sync failed",
                payload={"error": f"state_sync_error: {exc}", "state_sync_error": True},
            )
            raise

    services.event_store.append(
        task_id=task_id,
        session_id=str(session_id) if session_id else None,
        event_type=EventType.TASK_CANCELLED,
        status="cancelled",
        message="Task cancelled by API request",
        payload={"celery_task_id": task_id},
    )
    AsyncResult(task_id, app=celery_app).revoke(terminate=True)
    logger.info(
        "task cancelled",
        extra={
            "task_id": task_id,
            "session_id": str(session_id) if session_id else "-",
            "batch_id": str(record.get("batch_id") or "-"),
        },
    )
    return True


@app.post("/tasks")
async def submit_task(
    file: Annotated[UploadFile, File(...)],
    message: Annotated[str | None, Form()] = None,
    tipo: Annotated[str | None, Form()] = None,
    task_type: Annotated[str | None, Form()] = None,
    priority: Annotated[int | None, Form()] = None,
    agent_id: Annotated[str | None, Form()] = None,
    session_id: Annotated[str | None, Form()] = None,
) -> dict[str, object]:
    file_bytes = await file.read()
    result = _register_and_dispatch_task(
        file_bytes=file_bytes,
        file_name=file.filename,
        content_type=file.content_type,
        message=message,
        task_type=task_type or tipo,
        priority=priority,
        agent_id=agent_id,
        session_id=session_id,
    )
    return {
        "task_id": result["task_id"],
        "status": "queued",
        "requested_agent_id": result["requested_agent_id"],
        "queue": result["queue"],
    }


@app.post("/batches")
async def submit_batch(
    files: Annotated[list[UploadFile], File(...)],
    message: Annotated[str | None, Form()] = None,
    tipo: Annotated[str | None, Form()] = None,
    task_type: Annotated[str | None, Form()] = None,
    priority: Annotated[int | None, Form()] = None,
    agent_id: Annotated[str | None, Form()] = None,
    idempotency_key: Annotated[str | None, Form()] = None,
) -> dict[str, object]:
    batch_config = services.validator_service.validate_batch_submission(
        total_files=len(files),
        message=message,
        task_type=task_type or tipo,
        priority=priority,
        requested_agent_id=agent_id,
        idempotency_key=idempotency_key,
    )
    if batch_config.idempotency_key:
        existing_batch = services.batch_service.get_batch_by_idempotency_key(
            batch_config.idempotency_key
        )
        if existing_batch is not None:
            services.dispatch_service.reconcile_pending()
            existing_summary = services.batch_service.get_batch_with_tasks(existing_batch["id"])
            return {
                "batch_id": existing_summary["id"],
                "status": existing_summary["status"],
                "task_type": existing_summary["task_type"],
                "priority": existing_summary["priority"],
                "total_tasks": existing_summary["total_tasks"],
                "queue": settings.queue_for_task_type(existing_summary["task_type"]),
                "task_ids": [task["id"] for task in existing_summary.get("tasks", [])],
                "idempotency_reused": True,
            }

    batch_id = str(uuid.uuid4())
    task_items: list[dict[str, object]] = []
    staged_paths: list[str] = []
    for index, upload in enumerate(files, start=1):
        file_bytes = await upload.read()
        validated = services.validator_service.validate_submission(
            file_bytes=file_bytes,
            file_name=upload.filename,
            content_type=upload.content_type,
            message=batch_config.message,
            task_type=batch_config.task_type,
            priority=batch_config.priority,
            requested_agent_id=batch_config.requested_agent_id,
            requested_session_id=None,
        )
        task_id = str(uuid.uuid4())
        staged = services.staging_service.stage_upload(
            task_id=task_id,
            file_name=validated.file_name,
            file_bytes=file_bytes,
            batch_id=batch_id,
        )
        staged_paths.append(str(staged["staged_path"]))
        task_items.append(
            {
                "task_id": task_id,
                "file_name": validated.file_name,
                "task_type": validated.task_type,
                "message": validated.message,
                "priority": validated.priority,
                "requested_agent_id": validated.requested_agent_id,
                "batch_id": batch_id,
                "input_metadata": {
                    "content_type": validated.content_type,
                    "staged_path": staged["staged_path"],
                    "staged_size_bytes": staged["size_bytes"],
                    "batch_item_index": index,
                    "batch_total_tasks": batch_config.total_files,
                },
                "dispatch_queue": settings.queue_for_task_type(validated.task_type),
            }
        )

    try:
        batch_submission = services.batch_service.create_batch_submission(
            batch_id=batch_id,
            task_type=batch_config.task_type,
            message=batch_config.message,
            requested_agent_id=batch_config.requested_agent_id,
            priority=batch_config.priority,
            idempotency_key=batch_config.idempotency_key,
            task_items=task_items,
        )
    except Exception:
        services.staging_service.delete_staged_inputs(staged_paths)
        raise
    if not batch_submission["created"]:
        existing_summary = services.batch_service.get_batch_with_tasks(batch_submission["batch"]["id"])
        services.dispatch_service.reconcile_pending()
        return {
            "batch_id": existing_summary["id"],
            "status": existing_summary["status"],
            "task_type": existing_summary["task_type"],
            "priority": existing_summary["priority"],
            "total_tasks": existing_summary["total_tasks"],
            "queue": settings.queue_for_task_type(existing_summary["task_type"]),
            "task_ids": [task["id"] for task in existing_summary.get("tasks", [])],
            "idempotency_reused": True,
        }

    submitted_tasks: list[dict[str, object]] = []
    dispatch_summary = services.dispatch_service.dispatch_tasks(
        [str(task["id"]) for task in batch_submission["tasks"]]
    )
    for task in batch_submission["tasks"]:
        submitted_tasks.append(
            {
                "task_id": task["id"],
                "queue": settings.queue_for_task_type(task["task_type"]),
            }
        )

    logger.info(
        "batch submitted",
        extra={"task_id": "-", "session_id": "-", "batch_id": batch_submission["batch"]["id"]},
    )
    return {
        "batch_id": batch_submission["batch"]["id"],
        "status": "queued",
        "task_type": batch_config.task_type,
        "priority": batch_config.priority,
        "total_tasks": batch_config.total_files,
        "queue": settings.queue_for_task_type(batch_config.task_type),
        "task_ids": [task["task_id"] for task in submitted_tasks],
        "idempotency_reused": False,
        "dispatch_summary": dispatch_summary,
    }


@app.get("/tasks/{task_id}")
async def get_task_status(task_id: str) -> dict[str, object]:
    return services.task_service.get_task(task_id)


@app.get("/tasks/{task_id}/events")
async def get_task_events(task_id: str) -> dict[str, object]:
    task = services.task_service.get_task(task_id)
    events = services.task_service.list_events(task_id)
    logger.info(
        "task events requested",
        extra={"task_id": task_id, "session_id": task.get("session_id") or "-"},
    )
    return {
        "task_id": task_id,
        "count": len(events),
        "events": events,
    }


@app.get("/tasks")
async def list_all_tasks(
    status: str | None = Query(default=None),
) -> list[dict[str, object]]:
    return services.task_service.list_tasks(status=status)


@app.get("/batches")
async def list_all_batches() -> list[dict[str, object]]:
    return services.batch_service.list_batches()


@app.get("/batches/{batch_id}")
async def get_batch(batch_id: str) -> dict[str, object]:
    return services.batch_service.get_batch_with_tasks(batch_id)


@app.post("/dispatch/reconcile")
async def reconcile_dispatches(limit: int = Query(default=100, ge=1, le=1000)) -> dict[str, int]:
    return services.dispatch_service.reconcile_pending(limit=limit)


@app.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str) -> dict[str, str]:
    record = services.task_service.get_task(task_id)
    if record["status"] == TaskStatus.CANCELLED.value:
        return {"status": "cancelled"}
    if record["status"] in {TaskStatus.COMPLETED.value, TaskStatus.FAILED.value}:
        raise InvalidStateTransition(
            f"Invalid task transition: {record['status']} -> {TaskStatus.CANCELLED.value}"
        )

    _cancel_task_record(record)
    return {"status": "cancelled"}


@app.post("/batches/{batch_id}/cancel")
async def cancel_batch(batch_id: str) -> dict[str, object]:
    services.batch_service.get_batch(batch_id)
    tasks = services.task_service.list_tasks(batch_id=batch_id)
    cancelled_tasks = 0
    skipped_tasks = 0
    for record in tasks:
        if _cancel_task_record(record):
            cancelled_tasks += 1
        else:
            skipped_tasks += 1

    summary = services.batch_service.get_batch_with_tasks(batch_id)
    return {
        "batch_id": batch_id,
        "status": summary["status"],
        "cancelled_tasks": cancelled_tasks,
        "skipped_tasks": skipped_tasks,
        "counts": summary["counts"],
    }
