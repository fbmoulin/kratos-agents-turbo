"""FastAPI application exposing endpoints for task management.

This module defines the HTTP API used to submit documents for
processing, query task status, cancel tasks and perform basic
administrative operations. It assumes that a Supabase database has
been configured via environment variables and that a Celery worker
running the tasks defined in ``src.worker.tasks`` is active.

Endpoints:

* ``POST /tasks`` – Submit a new document for processing. Accepts
  multipart/form-data with ``file`` and ``message`` fields.
* ``GET /tasks/{task_id}`` – Retrieve the status and result of a
  specific task.
* ``GET /tasks`` – List tasks optionally filtered by status.
* ``POST /admin/cancel/{task_id}`` – Cancel a task by ID. This
  updates the DB state and revokes the corresponding Celery task.
* ``POST /admin/clear-queue`` – Clear all queued tasks (dangerous).

To run the API locally::

    uvicorn src.api.main:app --reload

Be sure to run a Celery worker in parallel::

    celery -A src.worker.celery_app.celery_app worker --loglevel=info
"""

import uuid
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from celery.result import AsyncResult

from src import db
from src.worker.celery_app import celery_app
from src.worker.tasks import process_document_task

app = FastAPI(title="Judicial Task Processing API", version="1.0.0")


@app.post("/tasks")
async def submit_task(
    file: UploadFile = File(...), message: str = Form("Gere despacho simples e objetivo"), tipo: str = Form("despacho"), priority: int = Form(0)
):
    """Submit a new task to process a document.

    The API generates a unique ID for the task, inserts a record into
    the database and schedules a Celery job to process the document.

    :param file: uploaded file (PDF or other supported format)
    :param message: instructions to pass to the AI
    :param tipo: classification of the piece: despacho, decisao or sentenca
    :param priority: optional task priority
    :return: a dict containing the task ID
    """
    # Read file contents (async to avoid blocking) and convert to bytes
    file_bytes = await file.read()
    # Generate deterministic id
    task_id = str(uuid.uuid4())
    # Insert into DB as queued
    db.insert_task(
        task_id=task_id,
        file_name=file.filename,
        tipo=tipo,
        status="queued",
        priority=priority,
    )
    db.insert_task_log(task_id, "queued")
    # Schedule Celery task with deterministic id so we can revoke
    process_document_task.apply_async(
        args=(task_id, file_bytes, file.filename, message),
        task_id=task_id,
    )
    return {"task_id": task_id}


@app.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    """Retrieve a task's status and result.

    :param task_id: unique id of the task
    :return: JSON representation of the task record
    """
    record = db.get_task(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return record


@app.get("/tasks")
async def list_all_tasks(status: Optional[str] = None) -> List[dict]:
    """List tasks optionally filtered by status.

    :param status: optional status filter
    :return: list of task records
    """
    tasks = db.list_tasks(status)
    return tasks


@app.post("/admin/cancel/{task_id}")
async def cancel_task(task_id: str):
    """Cancel a task by id.

    This operation updates the database status to ``cancelled`` and
    revokes the Celery task (terminating it if currently executing).

    :param task_id: unique id of the task
    :return: JSON message
    """
    record = db.get_task(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Task not found")
    # Update DB
    db.update_task_status(task_id, "cancelled")
    db.insert_task_log(task_id, "cancelled")
    # Revoke the Celery task
    AsyncResult(task_id, app=celery_app).revoke(terminate=True)
    return {"status": "cancelled"}


@app.post("/admin/clear-queue")
async def clear_queue():
    """Clear all queued tasks.

    This deletes tasks with status ``queued`` from the database. It
    does not affect tasks currently executing. Use with caution.
    """
    queued = db.list_tasks(status="queued")
    for task in queued:
        task_id = task["id"]
        # revoke any still in Celery if present
        AsyncResult(task_id, app=celery_app).revoke(terminate=True)
        db.update_task_status(task_id, "cancelled")
        db.insert_task_log(task_id, "cancelled by clear")
    return {"cleared": len(queued)}