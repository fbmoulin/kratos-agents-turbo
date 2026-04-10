"""Batch submission and read service."""

from __future__ import annotations

from collections import Counter
from typing import Any

from src import db
from src.core import NotFoundError
from src.services.task_service import TaskService


class BatchService:
    """Manage batch creation and operational summaries."""

    def __init__(self, task_service: TaskService) -> None:
        self.task_service = task_service

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
    ) -> dict[str, Any]:
        return db.create_batch(
            batch_id=batch_id,
            task_type=task_type,
            message=message,
            requested_agent_id=requested_agent_id,
            priority=priority,
            total_tasks=total_tasks,
            input_metadata=input_metadata,
        )

    def get_batch(self, batch_id: str) -> dict[str, Any]:
        batch = db.get_batch(batch_id)
        if batch is None:
            raise NotFoundError(f"Batch '{batch_id}' not found")
        return batch

    def list_batches(self) -> list[dict[str, Any]]:
        return [self._summary_for_batch(batch, include_tasks=False) for batch in db.list_batches()]

    def get_batch_with_tasks(self, batch_id: str) -> dict[str, Any]:
        batch = self.get_batch(batch_id)
        return self._summary_for_batch(batch, include_tasks=True)

    def _summary_for_batch(
        self,
        batch: dict[str, Any],
        *,
        include_tasks: bool,
    ) -> dict[str, Any]:
        tasks = self.task_service.list_tasks(batch_id=batch["id"])
        tasks.sort(
            key=lambda task: (
                int(task.get("input_metadata", {}).get("batch_item_index") or 0),
                str(task.get("created_at") or ""),
            )
        )
        counts = Counter(task["status"] for task in tasks)
        total_tasks = batch["total_tasks"]
        if counts["cancelled"] == total_tasks:
            status = "cancelled"
        elif counts["completed"] == total_tasks:
            status = "completed"
        elif counts["failed"] == total_tasks:
            status = "failed"
        elif counts["queued"] == total_tasks:
            status = "queued"
        elif counts["running"] > 0 or counts["queued"] > 0:
            status = "running"
        else:
            status = "partial"

        summary = {
            **batch,
            "status": status,
            "counts": {
                "queued": counts["queued"],
                "running": counts["running"],
                "completed": counts["completed"],
                "failed": counts["failed"],
                "cancelled": counts["cancelled"],
            },
        }
        if include_tasks:
            summary["tasks"] = [
                {
                    "id": task["id"],
                    "file_name": task["file_name"],
                    "status": task["status"],
                    "priority": task["priority"],
                    "session_id": task.get("session_id"),
                    "batch_item_index": task.get("input_metadata", {}).get("batch_item_index"),
                }
                for task in tasks
            ]
        return summary
