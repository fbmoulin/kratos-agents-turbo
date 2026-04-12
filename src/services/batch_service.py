"""Batch submission and read service."""

from __future__ import annotations

from typing import Any

from psycopg.errors import UniqueViolation

from src import db
from src.core import NotFoundError
from src.events import EventStore, EventType
from src.services.task_service import TaskService


class BatchService:
    """Manage batch creation and operational summaries."""

    def __init__(self, *, task_service: TaskService, event_store: EventStore) -> None:
        self.task_service = task_service
        self.event_store = event_store

    def create_batch(
        self,
        *,
        batch_id: str,
        task_type: str,
        message: str,
        requested_agent_id: str | None,
        priority: int,
        total_tasks: int,
        input_metadata: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        conn: Any | None = None,
    ) -> dict[str, Any]:
        return db.create_batch(
            batch_id=batch_id,
            task_type=task_type,
            message=message,
            requested_agent_id=requested_agent_id,
            priority=priority,
            total_tasks=total_tasks,
            input_metadata=input_metadata,
            idempotency_key=idempotency_key,
            conn=conn,
        )

    def create_batch_submission(
        self,
        *,
        batch_id: str,
        task_type: str,
        message: str,
        requested_agent_id: str | None,
        priority: int,
        idempotency_key: str | None,
        task_items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            with db.transaction() as conn:
                if idempotency_key:
                    existing_batch = db.get_batch_by_idempotency_key(idempotency_key, conn=conn)
                    if existing_batch is not None:
                        return {
                            "created": False,
                            "batch": existing_batch,
                            "tasks": self.task_service.list_tasks(
                                batch_id=existing_batch["id"],
                                conn=conn,
                            ),
                        }

                batch = self.create_batch(
                    batch_id=batch_id,
                    task_type=task_type,
                    message=message,
                    requested_agent_id=requested_agent_id,
                    priority=priority,
                    total_tasks=len(task_items),
                    input_metadata={"submission_mode": "batch"},
                    idempotency_key=idempotency_key,
                    conn=conn,
                )

                created_tasks: list[dict[str, Any]] = []
                for item in task_items:
                    dispatch_queue = item.pop("dispatch_queue")
                    created_task = self.task_service.create_task(conn=conn, **item)
                    created_tasks.append(created_task)
                    self.event_store.append(
                        task_id=created_task["id"],
                        session_id=None,
                        event_type=EventType.TASK_CREATED,
                        status="queued",
                        message="Task registered and queued",
                        payload={
                            "batch_id": batch["id"],
                            "batch_item_index": created_task.get("input_metadata", {}).get(
                                "batch_item_index"
                            ),
                            "file_name": created_task["file_name"],
                            "task_type": created_task["task_type"],
                            "priority": created_task["priority"],
                            "requested_agent_id": created_task["requested_agent_id"],
                        },
                        conn=conn,
                    )
                    db.create_task_dispatch(
                        task_id=created_task["id"],
                        queue_name=dispatch_queue,
                        payload={
                            "task_id": created_task["id"],
                            "staged_path": created_task.get("input_metadata", {}).get(
                                "staged_path"
                            ),
                            "file_name": created_task["file_name"],
                            "message": created_task["message"],
                            "task_type": created_task["task_type"],
                            "priority": created_task["priority"],
                            "requested_agent_id": created_task.get("requested_agent_id"),
                            "requested_session_id": None,
                            "content_type": created_task.get("input_metadata", {}).get(
                                "content_type",
                                "application/pdf",
                            ),
                            "batch_id": batch["id"],
                        },
                        conn=conn,
                    )
                return {
                    "created": True,
                    "batch": batch,
                    "tasks": created_tasks,
                }
        except UniqueViolation:
            if not idempotency_key:
                raise
            existing_batch = self.get_batch_by_idempotency_key(idempotency_key)
            if existing_batch is None:
                raise
            return {
                "created": False,
                "batch": existing_batch,
                "tasks": self.task_service.list_tasks(batch_id=existing_batch["id"]),
            }

    def get_batch(self, batch_id: str) -> dict[str, Any]:
        batch = db.get_batch(batch_id)
        if batch is None:
            raise NotFoundError(f"Batch '{batch_id}' not found")
        return batch

    def get_batch_by_idempotency_key(self, idempotency_key: str) -> dict[str, Any] | None:
        return db.get_batch_by_idempotency_key(idempotency_key)

    def list_batches(
        self,
        *,
        task_type: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        return [
            self._build_batch_summary(summary)
            for summary in db.list_batch_summaries(
                task_type=task_type,
                status=status,
                limit=limit,
                offset=offset,
            )
        ]

    def get_batch_with_tasks(self, batch_id: str) -> dict[str, Any]:
        batch = db.get_batch_summary(batch_id)
        if batch is None:
            raise NotFoundError(f"Batch '{batch_id}' not found")
        summary = self._build_batch_summary(batch)
        summary["tasks"] = [
            {
                "id": task["id"],
                "file_name": task["file_name"],
                "status": task["status"],
                "priority": task["priority"],
                "session_id": task.get("session_id"),
                "batch_item_index": task.get("batch_item_index"),
            }
            for task in db.list_batch_task_views(batch_id)
        ]
        return summary

    @staticmethod
    def _build_batch_summary(batch: dict[str, Any]) -> dict[str, Any]:
        return {
            **batch,
            "status": batch["status"],
            "counts": {
                "queued": int(batch.get("queued_count") or 0),
                "running": int(batch.get("running_count") or 0),
                "completed": int(batch.get("completed_count") or 0),
                "failed": int(batch.get("failed_count") or 0),
                "cancelled": int(batch.get("cancelled_count") or 0),
            },
        }
