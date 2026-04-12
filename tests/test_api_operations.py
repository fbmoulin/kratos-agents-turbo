from __future__ import annotations

from fastapi.testclient import TestClient
from src.api.main import app


def test_metrics_endpoint_returns_prometheus_payload(monkeypatch):
    calls: dict[str, object] = {}

    monkeypatch.setattr(
        "src.api.main.generate_metrics_payload",
        lambda operations_service, ttl_seconds=15: (
            calls.setdefault(
                "generate_metrics_payload",
                {
                    "operations_service": operations_service,
                    "ttl_seconds": ttl_seconds,
                },
            )
            and b"# HELP kratos_tasks_total test\nkratos_tasks_total 1\n"
        ),
    )

    client = TestClient(app)
    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.text == "# HELP kratos_tasks_total test\nkratos_tasks_total 1\n"
    assert response.headers["content-type"].startswith("text/plain; version=0.0.4")
    assert calls["generate_metrics_payload"]["ttl_seconds"] == 15


def test_operations_summary_returns_operational_snapshot(monkeypatch):
    monkeypatch.setattr(
        "src.api.main.services.operations_service.summary",
        lambda **kwargs: {
            "queue_backlog": [
                {
                    "queue_name": "legal-despacho",
                    "task_type": "despacho",
                    "queued_tasks": 3,
                    "running_tasks": 1,
                    "pending_dispatches": 1,
                    "failed_dispatches": 0,
                    "dispatched_but_queued_tasks": 0,
                }
            ],
            "open_batches": [{"id": "batch-1", "status": "running"}],
            "pending_dispatches": [{"task_id": "task-1", "status": "failed"}],
            "dispatched_but_queued": [{"id": "task-3", "status": "queued"}],
            "stuck_tasks": [{"id": "task-2", "status": "running"}],
            "failed_tasks_by_type": [{"task_type": "decisao", "total": 1}],
            "worker_heartbeats": [{"worker": "despacho@host", "status": "pong"}],
            "query": kwargs,
        },
    )

    client = TestClient(app)
    response = client.get(
        "/operations/summary?task_type=despacho&limit=10&pending_dispatch_after_minutes=7&stuck_task_after_minutes=45"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["queue_backlog"][0]["queue_name"] == "legal-despacho"
    assert payload["open_batches"][0]["id"] == "batch-1"
    assert payload["pending_dispatches"][0]["task_id"] == "task-1"
    assert payload["dispatched_but_queued"][0]["id"] == "task-3"
    assert payload["stuck_tasks"][0]["id"] == "task-2"
    assert payload["failed_tasks_by_type"][0]["task_type"] == "decisao"
    assert payload["worker_heartbeats"][0]["worker"] == "despacho@host"
    assert payload["query"] == {
        "task_type": "despacho",
        "pending_dispatch_after_minutes": 7,
        "stuck_task_after_minutes": 45,
        "limit": 10,
    }
