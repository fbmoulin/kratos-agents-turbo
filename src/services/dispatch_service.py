"""Broker dispatch coordination backed by a PostgreSQL outbox."""

from __future__ import annotations

from typing import Any

from src import db
from src.core import get_logger
from src.events import EventStore, EventType
from src.worker.celery_app import celery_app


class DispatchService:
    """Publish queued task payloads from a persistent outbox."""

    def __init__(self, event_store: EventStore) -> None:
        self.event_store = event_store
        self.logger = get_logger(__name__)

    def publish(
        self,
        *,
        task_id: str,
        queue: str,
        payload: dict[str, Any],
    ) -> None:
        celery_app.send_task(
            "process_document",
            kwargs=payload,
            task_id=task_id,
            queue=queue,
        )

    def dispatch_task(self, task_id: str) -> dict[str, Any]:
        record = db.get_task_dispatch(task_id)
        if record is None:
            raise ValueError(f"Dispatch record for task '{task_id}' not found")
        return self._dispatch_record(record)

    def dispatch_tasks(self, task_ids: list[str]) -> dict[str, int]:
        dispatched = 0
        failed = 0
        for task_id in task_ids:
            result = self.dispatch_task(task_id)
            if result["status"] == "dispatched":
                dispatched += 1
            else:
                failed += 1
        return {"dispatched": dispatched, "failed": failed}

    def reconcile_pending(self, *, limit: int = 100) -> dict[str, int]:
        records = db.list_task_dispatches(limit=limit)
        dispatched = 0
        failed = 0
        for record in records:
            result = self._dispatch_record(record)
            if result["status"] == "dispatched":
                dispatched += 1
            else:
                failed += 1
        return {"processed": len(records), "dispatched": dispatched, "failed": failed}

    def _dispatch_record(self, record: dict[str, Any]) -> dict[str, Any]:
        task_id = str(record["task_id"])
        queue_name = str(record["queue_name"])
        payload = record["payload"]
        attempts = int(record.get("attempts") or 0)
        try:
            self.publish(task_id=task_id, queue=queue_name, payload=payload)
            updated = db.update_task_dispatch(
                task_id,
                status="dispatched",
                attempts=attempts + 1,
                last_error=None,
                dispatched_at=db.utc_now(),
            )
            self.event_store.append(
                task_id=task_id,
                session_id=None,
                event_type=EventType.TASK_DISPATCHED,
                status="queued",
                message="Task published to broker",
                payload={"queue": queue_name},
            )
            self.logger.info(
                "task dispatched",
                extra={"task_id": task_id, "session_id": "-", "batch_id": "-"},
            )
            return updated
        except Exception as exc:
            updated = db.update_task_dispatch(
                task_id,
                status="failed",
                attempts=attempts + 1,
                last_error=str(exc),
            )
            try:
                self.event_store.append(
                    task_id=task_id,
                    session_id=None,
                    event_type=EventType.TASK_DISPATCH_FAILED,
                    status="queued",
                    message="Task dispatch failed",
                    payload={"queue": queue_name, "error": str(exc)},
                )
            except Exception:
                self.logger.exception(
                    "failed to persist dispatch failure event",
                    extra={"task_id": task_id, "session_id": "-", "batch_id": "-"},
                )
            self.logger.exception(
                "task dispatch failed",
                extra={"task_id": task_id, "session_id": "-", "batch_id": "-"},
            )
            return updated


__all__ = ["DispatchService"]
