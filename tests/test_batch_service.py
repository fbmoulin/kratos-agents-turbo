from __future__ import annotations

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
    monkeypatch.setattr(
        "src.services.batch_service.db.list_batches",
        lambda conn=None: [],
    )
    monkeypatch.setattr(
        "src.services.batch_service.db.get_batch",
        lambda batch_id, conn=None: {"id": batch_id, "total_tasks": 1},
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
