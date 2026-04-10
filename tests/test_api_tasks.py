from __future__ import annotations

from unittest.mock import Mock

from fastapi.testclient import TestClient

from src.api.main import app


def test_post_tasks_accepts_create_only_submission(monkeypatch):
    calls: dict[str, object] = {}

    def fake_create_task(**kwargs):
        calls["create_task"] = kwargs
        return kwargs

    def fake_append(**kwargs):
        calls["event"] = kwargs
        return kwargs

    def fake_apply_async(**kwargs):
        calls["apply_async"] = kwargs

    monkeypatch.setattr("src.api.main.services.task_service.create_task", fake_create_task)
    monkeypatch.setattr("src.api.main.services.event_store.append", fake_append)
    monkeypatch.setattr("src.api.main.process_document_task.apply_async", fake_apply_async)

    client = TestClient(app)
    response = client.post(
        "/tasks",
        files={"file": ("sample.pdf", b"%PDF-1.4 test document", "application/pdf")},
        data={"message": "Emitir minuta", "tipo": "despacho", "priority": "1"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "queued"
    assert calls["event"]["session_id"] is None
    assert calls["apply_async"]["kwargs"]["requested_session_id"] is None


def test_post_tasks_rejects_malformed_session_id():
    client = TestClient(app)
    response = client.post(
        "/tasks",
        files={"file": ("sample.pdf", b"%PDF-1.4 test document", "application/pdf")},
        data={"session_id": "not-a-uuid"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "session_id must be a valid UUID"


def test_post_tasks_rejects_any_session_id_on_create():
    client = TestClient(app)
    response = client.post(
        "/tasks",
        files={"file": ("sample.pdf", b"%PDF-1.4 test document", "application/pdf")},
        data={"session_id": "2e35c0ce-3bc9-4ad1-8bc9-a4e0af2241ee"},
    )

    assert response.status_code == 422
    assert "create-only" in response.json()["detail"]


def test_get_task_events_returns_ordered_envelope(monkeypatch):
    monkeypatch.setattr(
        "src.api.main.services.task_service.get_task",
        lambda task_id: {"id": task_id, "session_id": "session-1", "status": "running"},
    )
    monkeypatch.setattr(
        "src.api.main.services.task_service.list_events",
        lambda task_id: [
            {"event_type": "TASK_CREATED", "created_at": "2026-04-10T10:00:00Z"},
            {"event_type": "TASK_STARTED", "created_at": "2026-04-10T10:00:01Z"},
        ],
    )

    client = TestClient(app)
    response = client.get("/tasks/task-1/events")

    assert response.status_code == 200
    assert response.json() == {
        "task_id": "task-1",
        "count": 2,
        "events": [
            {"event_type": "TASK_CREATED", "created_at": "2026-04-10T10:00:00Z"},
            {"event_type": "TASK_STARTED", "created_at": "2026-04-10T10:00:01Z"},
        ],
    }


def test_get_task_events_returns_404_for_missing_task(monkeypatch):
    monkeypatch.setattr(
        "src.api.main.services.task_service.get_task",
        Mock(side_effect=Exception("should not be called")),
    )

    def raise_not_found(task_id):
        from src.core import NotFoundError

        raise NotFoundError(f"Task '{task_id}' not found")

    monkeypatch.setattr("src.api.main.services.task_service.get_task", raise_not_found)

    client = TestClient(app)
    response = client.get("/tasks/missing/events")

    assert response.status_code == 404
    assert "Task 'missing' not found" == response.json()["detail"]
