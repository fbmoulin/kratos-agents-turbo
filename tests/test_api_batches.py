from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.main import app


def test_post_batches_accepts_batch_submission(monkeypatch):
    calls: dict[str, object] = {"tasks": [], "events": [], "apply_async": []}

    def fake_create_batch(**kwargs):
        calls["batch"] = kwargs
        return kwargs

    def fake_create_task(**kwargs):
        calls["tasks"].append(kwargs)
        return kwargs

    def fake_append(**kwargs):
        calls["events"].append(kwargs)
        return kwargs

    def fake_stage_upload(**kwargs):
        return {
            "staged_path": f"/tmp/{kwargs['task_id']}-{kwargs['file_name']}",
            "size_bytes": len(kwargs["file_bytes"]),
        }

    def fake_apply_async(**kwargs):
        calls["apply_async"].append(kwargs)

    monkeypatch.setattr("src.api.main.services.batch_service.create_batch", fake_create_batch)
    monkeypatch.setattr("src.api.main.services.task_service.create_task", fake_create_task)
    monkeypatch.setattr("src.api.main.services.event_store.append", fake_append)
    monkeypatch.setattr("src.api.main.services.staging_service.stage_upload", fake_stage_upload)
    monkeypatch.setattr("src.api.main.process_document_task.apply_async", fake_apply_async)

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
    assert calls["batch"]["total_tasks"] == 2
    assert len(calls["tasks"]) == 2
    assert calls["tasks"][0]["batch_id"] == payload["batch_id"]
    assert calls["tasks"][0]["input_metadata"]["batch_item_index"] == 1
    assert calls["tasks"][1]["input_metadata"]["batch_item_index"] == 2
    assert calls["apply_async"][0]["queue"] == "legal-despacho"
    assert calls["apply_async"][0]["kwargs"]["batch_id"] == payload["batch_id"]


def test_post_batches_rejects_above_max_limit():
    client = TestClient(app)
    files = [
        ("files", (f"doc-{index}.pdf", b"%PDF-1.4 test", "application/pdf"))
        for index in range(101)
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
    monkeypatch.setattr(
        "src.api.main.services.batch_service.list_batches",
        lambda: [{"id": "batch-1", "status": "queued"}],
    )

    client = TestClient(app)
    response = client.get("/batches")

    assert response.status_code == 200
    assert response.json() == [{"id": "batch-1", "status": "queued"}]
