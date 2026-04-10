from __future__ import annotations

from fastapi.testclient import TestClient
from src.api.main import app


def test_post_batches_accepts_batch_submission(monkeypatch):
    calls: dict[str, object] = {}

    async def fake_submit_batch(**kwargs):
        calls["submit_batch"] = kwargs
        return {
            "batch_id": "batch-1",
            "status": "queued",
            "task_type": "despacho",
            "priority": 9,
            "total_tasks": 2,
            "queue": "legal-despacho",
            "task_ids": ["task-1", "task-2"],
            "idempotency_reused": False,
            "dispatch_summary": {"dispatched": 2, "failed": 0},
        }

    monkeypatch.setattr("src.api.main.services.submission_service.submit_batch", fake_submit_batch)

    client = TestClient(app)
    response = client.post(
        "/batches",
        files=[
            ("files", ("a.pdf", b"%PDF-1.4 A", "application/pdf")),
            ("files", ("b.pdf", b"%PDF-1.4 B", "application/pdf")),
        ],
        data={"message": "Gerar lotes", "tipo": "despacho"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["task_type"] == "despacho"
    assert payload["queue"] == "legal-despacho"
    assert payload["total_tasks"] == 2
    assert len(payload["task_ids"]) == 2
    assert len(calls["submit_batch"]["files"]) == 2
    assert calls["submit_batch"]["task_type"] == "despacho"
    assert payload["dispatch_summary"]["dispatched"] == 2


def test_post_batches_reuses_existing_idempotent_batch(monkeypatch):
    async def fake_submit_batch(**kwargs):
        return {
            "batch_id": "batch-existing",
            "status": "running",
            "task_type": "despacho",
            "priority": 9,
            "total_tasks": 2,
            "queue": "legal-despacho",
            "task_ids": ["task-1", "task-2"],
            "idempotency_reused": True,
        }

    monkeypatch.setattr(
        "src.api.main.services.submission_service.submit_batch",
        fake_submit_batch,
    )

    client = TestClient(app)
    response = client.post(
        "/batches",
        files=[("files", ("a.pdf", b"%PDF-1.4 A", "application/pdf"))],
        data={"message": "Gerar lotes", "tipo": "despacho", "idempotency_key": "batch-abc"},
    )

    assert response.status_code == 200
    assert response.json()["batch_id"] == "batch-existing"
    assert response.json()["idempotency_reused"] is True


def test_post_batches_rejects_above_max_limit():
    client = TestClient(app)
    files = [
        ("files", (f"doc-{index}.pdf", b"%PDF-1.4 test", "application/pdf")) for index in range(101)
    ]

    response = client.post(
        "/batches",
        files=files,
        data={"message": "Gerar lote", "tipo": "despacho"},
    )

    assert response.status_code == 422
    assert "max file count" in response.json()["detail"]


def test_get_batch_returns_summary(monkeypatch):
    monkeypatch.setattr(
        "src.api.main.services.batch_service.get_batch_with_tasks",
        lambda batch_id: {
            "id": batch_id,
            "status": "running",
            "counts": {"queued": 1, "running": 1, "completed": 0, "failed": 0, "cancelled": 0},
            "tasks": [],
        },
    )

    client = TestClient(app)
    response = client.get("/batches/batch-1")

    assert response.status_code == 200
    assert response.json()["id"] == "batch-1"


def test_list_batches_returns_summaries(monkeypatch):
    calls: dict[str, object] = {}

    def fake_list_batches(**kwargs):
        calls["list_batches"] = kwargs
        return [{"id": "batch-1", "status": "queued"}]

    monkeypatch.setattr(
        "src.api.main.services.batch_service.list_batches",
        fake_list_batches,
    )

    client = TestClient(app)
    response = client.get("/batches?limit=25&offset=10")

    assert response.status_code == 200
    assert response.json() == [{"id": "batch-1", "status": "queued"}]
    assert calls["list_batches"] == {"limit": 25, "offset": 10}


def test_reconcile_dispatches_endpoint(monkeypatch):
    monkeypatch.setattr(
        "src.api.main.services.dispatch_service.reconcile_pending",
        lambda limit=100: {"processed": limit, "dispatched": 2, "failed": 1},
    )

    client = TestClient(app)
    response = client.post("/dispatch/reconcile?limit=25")

    assert response.status_code == 200
    assert response.json() == {"processed": 25, "dispatched": 2, "failed": 1}


def test_post_batches_reports_recoverable_dispatch_failure(monkeypatch):
    async def fake_submit_batch(**kwargs):
        return {
            "batch_id": "batch-reconcile",
            "status": "queued",
            "task_type": "despacho",
            "priority": 9,
            "total_tasks": 1,
            "queue": "legal-despacho",
            "task_ids": ["task-1"],
            "idempotency_reused": False,
            "dispatch_summary": {"dispatched": 0, "failed": 1},
        }

    monkeypatch.setattr(
        "src.api.main.services.submission_service.submit_batch",
        fake_submit_batch,
    )

    client = TestClient(app)
    response = client.post(
        "/batches",
        files=[("files", ("a.pdf", b"%PDF-1.4 A", "application/pdf"))],
        data={"message": "Gerar lote", "tipo": "despacho", "idempotency_key": "batch-reconcile"},
    )

    assert response.status_code == 200
    assert response.json()["dispatch_summary"] == {"dispatched": 0, "failed": 1}
