from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.main import app


def test_post_batches_accepts_batch_submission(monkeypatch):
    calls: dict[str, object] = {"apply_async": []}

    def fake_stage_upload(**kwargs):
        return {
            "staged_path": f"/tmp/{kwargs['task_id']}-{kwargs['file_name']}",
            "size_bytes": len(kwargs["file_bytes"]),
        }

    def fake_apply_async(**kwargs):
        calls["apply_async"].append(kwargs)

    def fake_get_batch_by_idempotency_key(idempotency_key):
        calls["idempotency_lookup"] = idempotency_key
        return None

    def fake_create_batch_submission(**kwargs):
        calls["batch_submission"] = kwargs
        tasks = []
        for item in kwargs["task_items"]:
            tasks.append(
                {
                    "id": item["task_id"],
                    "file_name": item["file_name"],
                    "task_type": item["task_type"],
                    "message": item["message"],
                    "priority": item["priority"],
                    "requested_agent_id": item["requested_agent_id"],
                    "input_metadata": item["input_metadata"],
                }
            )
        return {
            "created": True,
            "batch": {"id": kwargs["batch_id"]},
            "tasks": tasks,
        }

    monkeypatch.setattr(
        "src.api.main.services.batch_service.get_batch_by_idempotency_key",
        fake_get_batch_by_idempotency_key,
    )
    monkeypatch.setattr(
        "src.api.main.services.batch_service.create_batch_submission",
        fake_create_batch_submission,
    )
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
    assert calls["batch_submission"]["idempotency_key"] is None
    assert len(calls["batch_submission"]["task_items"]) == 2
    assert calls["batch_submission"]["task_items"][0]["batch_id"] == payload["batch_id"]
    assert calls["batch_submission"]["task_items"][0]["input_metadata"]["batch_item_index"] == 1
    assert calls["batch_submission"]["task_items"][1]["input_metadata"]["batch_item_index"] == 2
    assert calls["apply_async"][0]["queue"] == "legal-despacho"
    assert calls["apply_async"][0]["kwargs"]["batch_id"] == payload["batch_id"]


def test_post_batches_reuses_existing_idempotent_batch(monkeypatch):
    monkeypatch.setattr(
        "src.api.main.services.batch_service.get_batch_by_idempotency_key",
        lambda idempotency_key: {"id": "batch-existing", "task_type": "despacho", "priority": 9, "total_tasks": 2},
    )
    monkeypatch.setattr(
        "src.api.main.services.batch_service.get_batch_with_tasks",
        lambda batch_id: {
            "id": batch_id,
            "status": "running",
            "task_type": "despacho",
            "priority": 9,
            "total_tasks": 2,
            "tasks": [{"id": "task-1"}, {"id": "task-2"}],
        },
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
