from __future__ import annotations

from types import SimpleNamespace

from src.core.metrics import generate_metrics_payload, reset_metrics_payload_cache


def _snapshot() -> dict[str, object]:
    return {
        "task_events": [],
        "task_statuses": [],
        "batch_statuses": [],
        "dispatch_statuses": [],
        "task_durations": [],
        "last_success_timestamps": [],
        "pending_dispatch_count": 0,
        "running_task_count": 0,
        "dispatched_but_queued_count": 2,
        "worker_heartbeats": [],
    }


def test_generate_metrics_payload_uses_short_lived_cache():
    reset_metrics_payload_cache()
    calls = {"metrics_snapshot": 0}

    def fake_metrics_snapshot():
        calls["metrics_snapshot"] += 1
        return _snapshot()

    operations_service = SimpleNamespace(metrics_snapshot=fake_metrics_snapshot)

    first = generate_metrics_payload(operations_service, ttl_seconds=60)
    second = generate_metrics_payload(operations_service, ttl_seconds=60)

    assert first == second
    assert calls["metrics_snapshot"] == 1


def test_generate_metrics_payload_includes_dispatched_but_queued_gauge():
    reset_metrics_payload_cache()
    operations_service = SimpleNamespace(metrics_snapshot=lambda: _snapshot())

    payload = generate_metrics_payload(operations_service, ttl_seconds=1).decode("utf-8")

    assert "kratos_dispatched_but_queued_tasks" in payload
    assert "kratos_dispatched_but_queued_tasks 2.0" in payload
