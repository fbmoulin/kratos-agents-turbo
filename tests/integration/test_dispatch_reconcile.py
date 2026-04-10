from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient
from src import db
from src.api.main import app
from src.api.main import services as api_services
from src.worker.tasks import process_document_task


def test_task_dispatch_failure_then_reconcile_and_worker_completion(
    monkeypatch,
):
    publish_calls = {"count": 0}

    def fake_publish(*, task_id: str, queue: str, payload: dict[str, object]) -> None:
        publish_calls["count"] += 1
        if publish_calls["count"] == 1:
            raise RuntimeError("broker unavailable")

    monkeypatch.setattr("src.api.main.services.dispatch_service.publish", fake_publish)

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/tasks",
        files={"file": ("sample.pdf", b"%PDF-1.4 integration test", "application/pdf")},
        data={"message": "Gerar minuta", "tipo": "despacho", "priority": "1"},
    )

    assert response.status_code == 202
    payload = response.json()
    task_id = payload["task_id"]
    assert payload["dispatch_summary"]["status"] == "failed"
    assert publish_calls["count"] == 1

    task = api_services.task_service.get_task(task_id)
    staged_path = task["input_metadata"]["staged_path"]
    dispatch = db.get_task_dispatch(task_id)
    assert dispatch is not None
    assert dispatch["status"] == "failed"

    reconcile_result = api_services.dispatch_service.reconcile_pending(limit=10)
    assert reconcile_result == {"processed": 1, "dispatched": 1, "failed": 0}
    assert publish_calls["count"] == 2
    assert db.get_task_dispatch(task_id)["status"] == "dispatched"

    class FakeAgent:
        def run(self, *, file_bytes, message, task_type, emit_step):
            emit_step("analysis", "mock-tool", {"file_size": len(file_bytes)})
            return SimpleNamespace(
                result_text="Minuta concluida",
                metadata={"result_type": "mock", "task_type": task_type},
            )

    monkeypatch.setattr(
        "src.worker.tasks.services.orchestrator_service.registry.build",
        lambda agent_id: FakeAgent(),
    )

    try:
        result = process_document_task.apply(
            kwargs={
                "task_id": task_id,
                "staged_path": staged_path,
                "file_name": "sample.pdf",
                "message": "Gerar minuta",
                "task_type": "despacho",
                "priority": 1,
                "requested_agent_id": None,
                "requested_session_id": None,
                "content_type": "application/pdf",
                "batch_id": None,
            }
        ).get()

        assert result["status"] == "completed"
        task = api_services.task_service.get_task(task_id)
        session_id = task["session_id"]
        assert task["status"] == "completed"
        assert session_id is not None
        session = db.get_session_by_task(task_id)
        assert session is not None
        assert session["id"] == session_id
        assert session["status"] == "completed"

        event_types = [
            event["event_type"] for event in api_services.task_service.list_events(task_id)
        ]
        assert "TASK_DISPATCH_FAILED" in event_types
        assert "TASK_DISPATCHED" in event_types
        assert "TASK_COMPLETED" in event_types
    finally:
        api_services.staging_service.delete_staged_input(staged_path)
