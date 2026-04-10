from __future__ import annotations

import uuid

from src.services.dispatch_service import DispatchService


class _EventStoreStub:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def append(self, **kwargs):
        self.calls.append(kwargs)
        return kwargs


def test_dispatch_service_coerces_uuid_task_id_before_publish(monkeypatch):
    published: dict[str, object] = {}
    updated: dict[str, object] = {}
    event_store = _EventStoreStub()
    service = DispatchService(event_store=event_store)

    def fake_publish(*, task_id: str, queue: str, payload: dict[str, object]) -> None:
        published["task_id"] = task_id
        published["queue"] = queue
        published["payload"] = payload

    def fake_update_task_dispatch(task_id: str, **fields):
        updated["task_id"] = task_id
        updated["fields"] = fields
        return {"task_id": task_id, "status": fields["status"]}

    monkeypatch.setattr(service, "publish", fake_publish)
    monkeypatch.setattr(
        "src.services.dispatch_service.db.claim_task_dispatch",
        lambda task_id: {
            "task_id": task_id,
            "queue_name": "legal-despacho",
            "payload": {"task_id": str(task_id), "file_name": "sample.pdf"},
            "status": "dispatching",
            "attempts": 1,
        },
    )
    monkeypatch.setattr(
        "src.services.dispatch_service.db.update_task_dispatch",
        fake_update_task_dispatch,
    )

    task_id = uuid.uuid4()
    result = service.dispatch_task(str(task_id))

    assert published["task_id"] == str(task_id)
    assert updated["task_id"] == str(task_id)
    assert result["status"] == "dispatched"
    assert event_store.calls[0]["task_id"] == str(task_id)


def test_dispatch_task_returns_existing_record_when_already_claimed(monkeypatch):
    event_store = _EventStoreStub()
    service = DispatchService(event_store=event_store)

    monkeypatch.setattr(
        "src.services.dispatch_service.db.claim_task_dispatch",
        lambda task_id: {
            "task_id": task_id,
            "queue_name": "legal-despacho",
            "payload": {"task_id": task_id},
            "status": "dispatched",
            "attempts": 1,
        },
    )

    result = service.dispatch_task("task-1")

    assert result["status"] == "dispatched"
    assert event_store.calls == []
