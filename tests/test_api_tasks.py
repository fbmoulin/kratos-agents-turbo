from __future__ import annotations

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

    monkeypatch.setattr("src.api.main.db.create_task", fake_create_task)
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
    assert calls["create_task"]["session_id"] is None
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
