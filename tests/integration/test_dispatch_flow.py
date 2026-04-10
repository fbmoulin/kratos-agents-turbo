from __future__ import annotations

import threading
import time
import uuid

from src import db
from src.events import EventStore
from src.services.dispatch_service import DispatchService


def _seed_dispatch(task_id: str) -> None:
    db.create_task(
        task_id=task_id,
        file_name=f"{task_id}.pdf",
        task_type="despacho",
        status="queued",
        message="Emitir minuta",
        priority=1,
        requested_agent_id="legal-document-agent",
        input_metadata={"staged_path": f"/tmp/{task_id}.pdf"},
    )
    db.create_task_dispatch(
        task_id=task_id,
        queue_name="legal-despacho",
        payload={"task_id": task_id, "file_name": f"{task_id}.pdf"},
    )


def test_reconcile_claims_each_dispatch_once_under_concurrency(monkeypatch):
    task_ids = [str(uuid.uuid4()) for _ in range(8)]
    for task_id in task_ids:
        _seed_dispatch(task_id)

    published: list[str] = []
    publish_lock = threading.Lock()
    service = DispatchService(event_store=EventStore())

    def fake_publish(*, task_id: str, queue: str, payload: dict[str, object]) -> None:
        del queue, payload
        with publish_lock:
            published.append(task_id)
        time.sleep(0.02)

    monkeypatch.setattr(service, "publish", fake_publish)

    results: list[dict[str, int]] = []
    result_lock = threading.Lock()

    def run_reconcile() -> None:
        summary = service.reconcile_pending(limit=len(task_ids))
        with result_lock:
            results.append(summary)

    threads = [threading.Thread(target=run_reconcile) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(published) == sorted(task_ids)
    assert len(published) == len(set(published)) == len(task_ids)
    assert sum(result["processed"] for result in results) == len(task_ids)
    assert all(db.get_task_dispatch(task_id)["status"] == "dispatched" for task_id in task_ids)
