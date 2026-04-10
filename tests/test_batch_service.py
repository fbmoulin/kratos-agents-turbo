from __future__ import annotations

import uuid
from contextlib import contextmanager
from types import SimpleNamespace

from src.services.batch_service import BatchService


def test_batch_service_reuses_existing_batch_by_idempotency_key(monkeypatch):
    service = BatchService(
        task_service=SimpleNamespace(
            list_tasks=lambda status=None, batch_id=None, conn=None: [
                {
                    "id": "task-1",
                    "status": "queued",
                    "file_name": "a.pdf",
                    "priority": 9,
                    "input_metadata": {},
                }
            ]
        ),
        event_store=SimpleNamespace(),
    )

    @contextmanager
    def fake_transaction():
        yield object()

    monkeypatch.setattr("src.services.batch_service.db.transaction", fake_transaction)
    monkeypatch.setattr(
        "src.services.batch_service.db.get_batch_by_idempotency_key",
        lambda idempotency_key, conn=None: {"id": "batch-1"},
    )
    result = service.create_batch_submission(
        batch_id="batch-new",
        task_type="despacho",
        message="Gerar lote",
        requested_agent_id=None,
        priority=9,
        idempotency_key="batch-key",
        task_items=[],
    )

    assert result["created"] is False
    assert result["batch"]["id"] == "batch-1"
    assert result["tasks"][0]["id"] == "task-1"


def test_batch_service_accepts_uuid_records_from_postgres(monkeypatch):
    event_calls: list[dict[str, object]] = []
    dispatch_calls: list[dict[str, object]] = []
    created_batch_id = uuid.uuid4()
    created_task_id = uuid.uuid4()

    service = BatchService(
        task_service=SimpleNamespace(
            create_task=lambda conn=None, **item: {
                "id": created_task_id,
                "file_name": item["file_name"],
                "task_type": item["task_type"],
                "message": item["message"],
                "priority": item["priority"],
                "requested_agent_id": item["requested_agent_id"],
                "input_metadata": item["input_metadata"],
            },
            list_tasks=lambda status=None, batch_id=None, conn=None: [],
        ),
        event_store=SimpleNamespace(append=lambda **kwargs: event_calls.append(kwargs)),
    )

    @contextmanager
    def fake_transaction():
        yield object()

    monkeypatch.setattr("src.services.batch_service.db.transaction", fake_transaction)
    monkeypatch.setattr(
        "src.services.batch_service.db.create_batch",
        lambda **kwargs: {"id": created_batch_id, "total_tasks": 1},
    )
    monkeypatch.setattr(
        "src.services.batch_service.db.create_task_dispatch",
        lambda **kwargs: dispatch_calls.append(kwargs),
    )

    result = service.create_batch_submission(
        batch_id=str(created_batch_id),
        task_type="despacho",
        message="Gerar lote",
        requested_agent_id=None,
        priority=9,
        idempotency_key=None,
        task_items=[
            {
                "task_id": str(created_task_id),
                "file_name": "batch-a.pdf",
                "task_type": "despacho",
                "message": "Gerar lote",
                "priority": 9,
                "requested_agent_id": None,
                "batch_id": str(created_batch_id),
                "input_metadata": {
                    "content_type": "application/pdf",
                    "staged_path": "/tmp/batch-a.pdf",
                    "batch_item_index": 1,
                },
                "dispatch_queue": "legal-despacho",
            }
        ],
    )

    assert result["created"] is True
    assert event_calls[0]["payload"]["batch_id"] == created_batch_id
    assert dispatch_calls[0]["payload"]["task_id"] == created_task_id
    assert dispatch_calls[0]["payload"]["batch_id"] == created_batch_id


def test_list_batches_uses_sql_batch_summaries(monkeypatch):
    service = BatchService(task_service=SimpleNamespace(), event_store=SimpleNamespace())
    monkeypatch.setattr(
        "src.services.batch_service.db.list_batch_summaries",
        lambda: [
            {
                "id": "batch-1",
                "status": "running",
                "queued_count": 1,
                "running_count": 2,
                "completed_count": 3,
                "failed_count": 0,
                "cancelled_count": 0,
                "total_tasks": 6,
            }
        ],
    )

    result = service.list_batches()

    assert result == [
        {
            "id": "batch-1",
            "status": "running",
            "queued_count": 1,
            "running_count": 2,
            "completed_count": 3,
            "failed_count": 0,
            "cancelled_count": 0,
            "total_tasks": 6,
            "counts": {
                "queued": 1,
                "running": 2,
                "completed": 3,
                "failed": 0,
                "cancelled": 0,
            },
        }
    ]


def test_get_batch_with_tasks_uses_sql_summary_and_task_projection(monkeypatch):
    service = BatchService(task_service=SimpleNamespace(), event_store=SimpleNamespace())
    monkeypatch.setattr(
        "src.services.batch_service.db.get_batch_summary",
        lambda batch_id: {
            "id": batch_id,
            "status": "completed",
            "queued_count": 0,
            "running_count": 0,
            "completed_count": 2,
            "failed_count": 0,
            "cancelled_count": 0,
            "total_tasks": 2,
        },
    )
    monkeypatch.setattr(
        "src.services.batch_service.db.list_batch_task_views",
        lambda batch_id: [
            {
                "id": "task-1",
                "file_name": "a.pdf",
                "status": "completed",
                "priority": 9,
                "session_id": "session-1",
                "batch_item_index": 1,
            }
        ],
    )

    result = service.get_batch_with_tasks("batch-1")

    assert result["counts"]["completed"] == 2
    assert result["tasks"] == [
        {
            "id": "task-1",
            "file_name": "a.pdf",
            "status": "completed",
            "priority": 9,
            "session_id": "session-1",
            "batch_item_index": 1,
        }
    ]
