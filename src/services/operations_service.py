"""Operational read models for batch runtime support."""

from __future__ import annotations

from typing import Any

from src import db
from src.services.batch_service import BatchService
from src.worker.celery_app import celery_app


class OperationsService:
    """Provide low-cardinality operational views for operators and metrics."""

    def __init__(self, *, batch_service: BatchService) -> None:
        self.batch_service = batch_service

    def list_pending_dispatches(
        self,
        *,
        older_than_minutes: int,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return db.list_pending_dispatches(
            older_than_minutes=older_than_minutes,
            limit=limit,
        )

    def list_stuck_tasks(
        self,
        *,
        older_than_minutes: int,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return db.list_stuck_tasks(
            older_than_minutes=older_than_minutes,
            limit=limit,
        )

    def summary(
        self,
        *,
        pending_dispatch_after_minutes: int,
        stuck_task_after_minutes: int,
        limit: int = 25,
    ) -> dict[str, Any]:
        open_batches = [
            batch
            for batch in self.batch_service.list_batches()
            if batch["status"] in {"queued", "running", "partial"}
        ][:limit]
        return {
            "open_batches": open_batches,
            "pending_dispatches": self.list_pending_dispatches(
                older_than_minutes=pending_dispatch_after_minutes,
                limit=limit,
            ),
            "stuck_tasks": self.list_stuck_tasks(
                older_than_minutes=stuck_task_after_minutes,
                limit=limit,
            ),
            "failed_tasks_by_type": db.get_failed_task_counts(),
            "worker_heartbeats": self.get_worker_heartbeats(),
        }

    def get_worker_heartbeats(self) -> list[dict[str, Any]]:
        try:
            inspector = celery_app.control.inspect(timeout=1.0)
            heartbeats = inspector.ping() or {}
        except Exception:
            heartbeats = {}
        return [
            {"worker": worker_name, "status": response.get("ok", "ok")}
            for worker_name, response in sorted(heartbeats.items())
        ]

    def metrics_snapshot(self) -> dict[str, Any]:
        return {
            "task_events": db.get_task_event_counts(),
            "task_statuses": db.get_task_status_counts(),
            "batch_statuses": db.get_batch_status_counts(),
            "dispatch_statuses": db.get_dispatch_status_counts(),
            "task_durations": db.get_task_duration_stats(),
            "last_success_timestamps": db.get_last_success_timestamps(),
            "pending_dispatch_count": db.count_pending_dispatches(),
            "running_task_count": db.count_running_tasks(),
            "worker_heartbeats": self.get_worker_heartbeats(),
        }
