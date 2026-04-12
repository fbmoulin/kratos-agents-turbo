"""FastAPI application for the legal agent execution platform."""

from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, File, Form, Query, UploadFile
from fastapi.responses import JSONResponse, Response

from src.core import (
    ApplicationError,
    InvalidStateTransition,
    NotFoundError,
    PersistenceError,
    ValidationError,
    configure_logging,
    get_logger,
    get_settings,
)
from src.core.metrics import generate_metrics_payload
from src.core.observability import configure_api_observability
from src.services import create_platform_services

settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger(__name__)
services = create_platform_services()

app = FastAPI(
    title="Kratos Agents Turbo API",
    version=settings.service_version,
)
configure_api_observability(app, settings)


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


@app.get("/metrics")
async def metrics() -> Response:
    payload = generate_metrics_payload(
        services.operations_service,
        ttl_seconds=settings.metrics_cache_ttl_seconds,
    )
    return Response(payload, media_type="text/plain; version=0.0.4; charset=utf-8")


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
    result = services.submission_service.submit_task(
        file_bytes=file_bytes,
        file_name=file.filename,
        content_type=file.content_type,
        message=message,
        task_type=task_type or tipo,
        priority=priority,
        agent_id=agent_id,
        session_id=session_id,
    )
    payload = {
        "task_id": result["task_id"],
        "status": "queued",
        "requested_agent_id": result["requested_agent_id"],
        "queue": result["queue"],
        "dispatch_summary": result["dispatch_summary"],
    }
    if result["dispatch_summary"]["status"] != "dispatched":
        return JSONResponse(status_code=202, content=payload)
    return payload


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
    result = await services.submission_service.submit_batch(
        files=files,
        message=message,
        task_type=task_type or tipo,
        priority=priority,
        agent_id=agent_id,
        idempotency_key=idempotency_key,
    )
    dispatch_summary = result.get("dispatch_summary")
    if (
        isinstance(dispatch_summary, dict)
        and not result.get("idempotency_reused", False)
        and int(dispatch_summary.get("failed") or 0) > 0
    ):
        return JSONResponse(status_code=202, content=result)
    return result


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
    task_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, object]]:
    return services.task_service.list_task_summaries(
        status=status,
        task_type=task_type,
        limit=limit,
        offset=offset,
    )


@app.get("/batches")
async def list_all_batches(
    status: str | None = Query(default=None),
    task_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, object]]:
    return services.batch_service.list_batches(
        status=status,
        task_type=task_type,
        limit=limit,
        offset=offset,
    )


@app.get("/batches/{batch_id}")
async def get_batch(batch_id: str) -> dict[str, object]:
    return services.batch_service.get_batch_with_tasks(batch_id)


@app.post("/dispatch/reconcile")
async def reconcile_dispatches(limit: int = Query(default=100, ge=1, le=1000)) -> dict[str, int]:
    return services.dispatch_service.reconcile_pending(limit=limit)


@app.get("/operations/summary")
async def get_operations_summary(
    task_type: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=200),
    pending_dispatch_after_minutes: int | None = Query(default=None, ge=0, le=1440),
    stuck_task_after_minutes: int | None = Query(default=None, ge=0, le=10080),
) -> dict[str, object]:
    return services.operations_service.summary(
        task_type=task_type,
        pending_dispatch_after_minutes=(
            pending_dispatch_after_minutes
            if pending_dispatch_after_minutes is not None
            else settings.operational_pending_dispatch_after_minutes
        ),
        stuck_task_after_minutes=(
            stuck_task_after_minutes
            if stuck_task_after_minutes is not None
            else settings.operational_stuck_task_after_minutes
        ),
        limit=limit,
    )


@app.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str) -> dict[str, str]:
    return services.cancellation_service.cancel_task(task_id)


@app.post("/batches/{batch_id}/cancel")
async def cancel_batch(batch_id: str) -> dict[str, object]:
    return services.cancellation_service.cancel_batch(batch_id)
