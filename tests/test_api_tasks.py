from __future__ import annotations

from unittest.mock import Mock

from fastapi.testclient import TestClient
from src.api.main import app


def test_post_tasks_accepts_create_only_submission(monkeypatch):
    calls: dict[str, object] = {}

    def fake_submit_task(**kwargs):
        calls["submit_task"] = kwargs
        return {
            "task_id": "task-1",
            "requested_agent_id": None,
            "queue": "legal-despacho",
            "dispatch_summary": {
                "status": "dispatched",
                "attempts": 1,
                "last_error": None,
            },
        }

    monkeypatch.setattr("src.api.main.services.submission_service.submit_task", fake_submit_task)

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/tasks",
        files={"file": ("sample.pdf", b"%PDF-1.4 test document", "application/pdf")},
        data={"message": "Emitir minuta", "tipo": "despacho", "priority": "1"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["queue"] == "legal-despacho"
    assert payload["dispatch_summary"] == {
        "status": "dispatched",
        "attempts": 1,
        "last_error": None,
    }
    assert calls["submit_task"]["file_name"] == "sample.pdf"
    assert calls["submit_task"]["task_type"] == "despacho"
    assert calls["submit_task"]["priority"] == 1


def test_post_tasks_returns_accepted_when_dispatch_fails(monkeypatch):
    monkeypatch.setattr(
        "src.api.main.services.submission_service.submit_task",
        lambda **kwargs: {
            "task_id": "task-1",
            "requested_agent_id": None,
            "queue": "legal-despacho",
            "dispatch_summary": {
                "status": "failed",
                "attempts": 1,
                "last_error": "broker down",
            },
        },
    )

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/tasks",
        files={"file": ("sample.pdf", b"%PDF-1.4 test document", "application/pdf")},
        data={"message": "Emitir minuta", "tipo": "despacho", "priority": "1"},
    )

    assert response.status_code == 202
    assert response.json()["dispatch_summary"] == {
        "status": "failed",
        "attempts": 1,
        "last_error": "broker down",
    }


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


def test_list_tasks_returns_summaries_with_pagination(monkeypatch):
    calls: dict[str, object] = {}

    def fake_list_task_summaries(**kwargs):
        calls["list_task_summaries"] = kwargs
        return [{"id": "task-1", "status": "queued", "file_name": "sample.pdf"}]

    monkeypatch.setattr(
        "src.api.main.services.task_service.list_task_summaries",
        fake_list_task_summaries,
    )

    client = TestClient(app)
    response = client.get("/tasks?status=queued&limit=25&offset=5")

    assert response.status_code == 200
    assert response.json() == [{"id": "task-1", "status": "queued", "file_name": "sample.pdf"}]
    assert calls["list_task_summaries"] == {
        "status": "queued",
        "limit": 25,
        "offset": 5,
    }
