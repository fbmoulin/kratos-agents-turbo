"""Submission orchestration for single-task and batch create flows."""

from __future__ import annotations

import uuid
from typing import Any

from src import db
from src.core import get_logger
from src.events import EventStore, EventType
from src.services.batch_service import BatchService
from src.services.dispatch_service import DispatchService
from src.services.staging_service import StagingService
from src.services.task_service import TaskService
from src.services.validator_service import ValidatorService


class SubmissionService:
    """Handle create/stage/persist/dispatch for task and batch submissions."""

    def __init__(
        self,
        *,
        validator_service: ValidatorService,
        staging_service: StagingService,
        task_service: TaskService,
        batch_service: BatchService,
        dispatch_service: DispatchService,
        event_store: EventStore,
        settings: Any,
    ) -> None:
        self.validator_service = validator_service
        self.staging_service = staging_service
        self.task_service = task_service
        self.batch_service = batch_service
        self.dispatch_service = dispatch_service
        self.event_store = event_store
        self.settings = settings
        self.logger = get_logger(__name__)

    def submit_task(
        self,
        *,
        file_bytes: bytes,
        file_name: str | None,
        content_type: str | None,
        message: str | None,
        task_type: str | None,
        priority: int | None,
        agent_id: str | None,
        session_id: str | None,
    ) -> dict[str, object]:
        prepared = self._prepare_task_submission(
            file_bytes=file_bytes,
            file_name=file_name,
            content_type=content_type,
            message=message,
            task_type=task_type,
            priority=priority,
            agent_id=agent_id,
            session_id=session_id,
        )

        try:
            with db.transaction() as conn:
                self.task_service.create_task(
                    task_id=str(prepared["task_id"]),
                    file_name=str(prepared["file_name"]),
                    task_type=str(prepared["task_type"]),
                    message=str(prepared["message"]),
                    priority=int(prepared["priority"]),
                    requested_agent_id=prepared["requested_agent_id"],
                    input_metadata=dict(prepared["input_metadata"]),
                    conn=conn,
                )
                self.event_store.append(
                    task_id=str(prepared["task_id"]),
                    session_id=None,
                    event_type=EventType.TASK_CREATED,
                    status="queued",
                    message="Task registered and queued",
                    payload={
                        "batch_id": None,
                        "batch_item_index": None,
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
                        "batch_id": None,
                    },
                    conn=conn,
                )
        except Exception:
            self.staging_service.delete_staged_input(str(prepared["staged_path"]))
            raise

        dispatch_result = self.dispatch_service.dispatch_task(str(prepared["task_id"]))
        self.logger.info(
            "task submitted",
            extra={
                "task_id": str(prepared["task_id"]),
                "session_id": "-",
                "batch_id": "-",
            },
        )
        return {
            "task_id": prepared["task_id"],
            "task_type": prepared["task_type"],
            "priority": prepared["priority"],
            "requested_agent_id": prepared["requested_agent_id"],
            "queue": prepared["queue"],
            "dispatch_summary": {
                "status": dispatch_result["status"],
                "attempts": int(dispatch_result.get("attempts") or 0),
                "last_error": dispatch_result.get("last_error"),
            },
        }

    async def submit_batch(
        self,
        *,
        files: list[Any],
        message: str | None,
        task_type: str | None,
        priority: int | None,
        agent_id: str | None,
        idempotency_key: str | None,
    ) -> dict[str, object]:
        batch_config = self.validator_service.validate_batch_submission(
            total_files=len(files),
            message=message,
            task_type=task_type,
            priority=priority,
            requested_agent_id=agent_id,
            idempotency_key=idempotency_key,
        )
        if batch_config.idempotency_key:
            existing_batch = self.batch_service.get_batch_by_idempotency_key(
                batch_config.idempotency_key
            )
            if existing_batch is not None:
                self.dispatch_service.reconcile_pending()
                existing_summary = self.batch_service.get_batch_with_tasks(existing_batch["id"])
                return self._build_existing_batch_response(existing_summary)

        batch_id = str(uuid.uuid4())
        task_items: list[dict[str, object]] = []
        staged_paths: list[str] = []
        cumulative_bytes = 0
        try:
            for index, upload in enumerate(files, start=1):
                upload_metadata = self.validator_service.validate_upload_metadata(
                    file_name=getattr(upload, "filename", None),
                    content_type=getattr(upload, "content_type", None),
                )
                task_id = str(uuid.uuid4())
                staged = await self.staging_service.stage_upload_stream(
                    task_id=task_id,
                    file_name=upload_metadata.file_name,
                    upload_file=upload,
                    max_bytes=self.settings.max_upload_bytes,
                    batch_id=batch_id,
                )
                self.validator_service.validate_file_size(int(staged["size_bytes"]))
                staged_paths.append(str(staged["staged_path"]))
                cumulative_bytes += int(staged["size_bytes"])
                self.validator_service.validate_batch_total_bytes(cumulative_bytes)
                task_items.append(
                    {
                        "task_id": task_id,
                        "file_name": upload_metadata.file_name,
                        "task_type": batch_config.task_type,
                        "message": batch_config.message,
                        "priority": batch_config.priority,
                        "requested_agent_id": batch_config.requested_agent_id,
                        "batch_id": batch_id,
                        "input_metadata": {
                            "content_type": upload_metadata.content_type,
                            "staged_path": staged["staged_path"],
                            "staged_size_bytes": staged["size_bytes"],
                            "batch_item_index": index,
                            "batch_total_tasks": batch_config.total_files,
                        },
                        "dispatch_queue": self.settings.queue_for_task_type(batch_config.task_type),
                    }
                )
        except Exception:
            self.staging_service.delete_staged_inputs(staged_paths)
            raise

        try:
            batch_submission = self.batch_service.create_batch_submission(
                batch_id=batch_id,
                task_type=batch_config.task_type,
                message=batch_config.message,
                requested_agent_id=batch_config.requested_agent_id,
                priority=batch_config.priority,
                idempotency_key=batch_config.idempotency_key,
                task_items=task_items,
            )
        except Exception:
            self.staging_service.delete_staged_inputs(staged_paths)
            raise

        if not batch_submission["created"]:
            existing_summary = self.batch_service.get_batch_with_tasks(
                batch_submission["batch"]["id"]
            )
            self.dispatch_service.reconcile_pending()
            return self._build_existing_batch_response(existing_summary)

        submitted_tasks = [
            {
                "task_id": task["id"],
                "queue": self.settings.queue_for_task_type(task["task_type"]),
            }
            for task in batch_submission["tasks"]
        ]
        dispatch_summary = self.dispatch_service.dispatch_tasks(
            [str(task["id"]) for task in batch_submission["tasks"]]
        )
        self.logger.info(
            "batch submitted",
            extra={
                "task_id": "-",
                "session_id": "-",
                "batch_id": batch_submission["batch"]["id"],
            },
        )
        return {
            "batch_id": batch_submission["batch"]["id"],
            "status": "queued",
            "task_type": batch_config.task_type,
            "priority": batch_config.priority,
            "total_tasks": batch_config.total_files,
            "queue": self.settings.queue_for_task_type(batch_config.task_type),
            "task_ids": [task["task_id"] for task in submitted_tasks],
            "idempotency_reused": False,
            "dispatch_summary": dispatch_summary,
        }

    def _prepare_task_submission(
        self,
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
        validated = self.validator_service.validate_submission(
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
        staged = self.staging_service.stage_upload(
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
            "queue": self.settings.queue_for_task_type(validated.task_type),
        }

    def _build_existing_batch_response(self, existing_summary: dict[str, Any]) -> dict[str, object]:
        return {
            "batch_id": existing_summary["id"],
            "status": existing_summary["status"],
            "task_type": existing_summary["task_type"],
            "priority": existing_summary["priority"],
            "total_tasks": existing_summary["total_tasks"],
            "queue": self.settings.queue_for_task_type(existing_summary["task_type"]),
            "task_ids": [task["id"] for task in existing_summary.get("tasks", [])],
            "idempotency_reused": True,
        }
