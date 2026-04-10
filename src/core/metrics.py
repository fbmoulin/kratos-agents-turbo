"""Prometheus exposition helpers backed by cached operational read models."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from time import monotonic

from prometheus_client import CollectorRegistry, generate_latest
from prometheus_client.core import GaugeMetricFamily

from src.services.operations_service import OperationsService


class OperationalMetricsCollector:
    """Collect low-cardinality metrics from Postgres and Celery runtime views."""

    def __init__(self, operations_service: OperationsService) -> None:
        self.operations_service = operations_service

    def collect(self):  # type: ignore[override]
        snapshot = self.operations_service.metrics_snapshot()

        task_events = GaugeMetricFamily(
            "kratos_task_events_total",
            "Total task events grouped by task type and event type.",
            labels=["task_type", "event_type"],
        )
        for row in snapshot["task_events"]:
            task_events.add_metric([row["task_type"], row["event_type"]], row["total"])
        yield task_events

        task_statuses = GaugeMetricFamily(
            "kratos_tasks_total",
            "Current task totals grouped by task type and status.",
            labels=["task_type", "status"],
        )
        for row in snapshot["task_statuses"]:
            task_statuses.add_metric([row["task_type"], row["status"]], row["total"])
        yield task_statuses

        batch_statuses = GaugeMetricFamily(
            "kratos_batches_total",
            "Current batch totals grouped by task type and derived status.",
            labels=["task_type", "status"],
        )
        for row in snapshot["batch_statuses"]:
            batch_statuses.add_metric([row["task_type"], row["status"]], row["total"])
        yield batch_statuses

        dispatch_statuses = GaugeMetricFamily(
            "kratos_dispatch_outbox_total",
            "Current task dispatch outbox totals grouped by status.",
            labels=["status"],
        )
        for row in snapshot["dispatch_statuses"]:
            dispatch_statuses.add_metric([row["status"]], row["total"])
        yield dispatch_statuses

        task_duration_avg = GaugeMetricFamily(
            "kratos_task_duration_seconds_avg",
            "Average completed task duration in seconds grouped by task type and final status.",
            labels=["task_type", "status"],
        )
        task_duration_max = GaugeMetricFamily(
            "kratos_task_duration_seconds_max",
            "Maximum completed task duration in seconds grouped by task type and final status.",
            labels=["task_type", "status"],
        )
        for row in snapshot["task_durations"]:
            labels = [row["task_type"], row["status"]]
            task_duration_avg.add_metric(labels, row["avg_seconds"])
            task_duration_max.add_metric(labels, row["max_seconds"])
        yield task_duration_avg
        yield task_duration_max

        pending_dispatches = GaugeMetricFamily(
            "kratos_pending_dispatches",
            "Count of pending or failed dispatches awaiting reconcile.",
        )
        pending_dispatches.add_metric([], snapshot["pending_dispatch_count"])
        yield pending_dispatches

        running_tasks = GaugeMetricFamily(
            "kratos_running_tasks_current",
            "Count of tasks currently marked as running.",
        )
        running_tasks.add_metric([], snapshot["running_task_count"])
        yield running_tasks

        dispatched_but_queued = GaugeMetricFamily(
            "kratos_dispatched_but_queued_tasks",
            "Count of queued tasks that were already marked as dispatched.",
        )
        dispatched_but_queued.add_metric([], snapshot["dispatched_but_queued_count"])
        yield dispatched_but_queued

        workers = GaugeMetricFamily(
            "kratos_workers_active",
            "Count of Celery workers answering inspect ping.",
        )
        workers.add_metric([], len(snapshot["worker_heartbeats"]))
        yield workers

        worker_status = GaugeMetricFamily(
            "kratos_worker_up",
            "Worker liveness indicator by Celery worker name.",
            labels=["worker"],
        )
        for row in snapshot["worker_heartbeats"]:
            worker_status.add_metric([row["worker"]], 1)
        yield worker_status

        last_success = GaugeMetricFamily(
            "kratos_last_success_timestamp_seconds",
            "Unix timestamp of the last successful task completion by task type.",
            labels=["task_type"],
        )
        for row in snapshot["last_success_timestamps"]:
            last_success.add_metric([row["task_type"]], row["finished_at_epoch"])
        yield last_success


@dataclass
class _MetricsPayloadCache:
    ttl_seconds: int
    payload: bytes | None = None
    expires_at: float = 0.0
    lock: Lock = field(default_factory=Lock)

    def get_or_build(self, operations_service: OperationsService) -> bytes:
        now = monotonic()
        if self.payload is not None and now < self.expires_at:
            return self.payload
        with self.lock:
            now = monotonic()
            if self.payload is not None and now < self.expires_at:
                return self.payload
            registry = CollectorRegistry()
            registry.register(OperationalMetricsCollector(operations_service))
            self.payload = generate_latest(registry)
            self.expires_at = now + max(self.ttl_seconds, 1)
            return self.payload


_metrics_payload_cache: _MetricsPayloadCache | None = None


def reset_metrics_payload_cache() -> None:
    global _metrics_payload_cache
    _metrics_payload_cache = None


def generate_metrics_payload(
    operations_service: OperationsService,
    *,
    ttl_seconds: int = 15,
) -> bytes:
    """Return a Prometheus text payload backed by a short-lived in-memory cache."""

    global _metrics_payload_cache
    if (
        _metrics_payload_cache is None
        or _metrics_payload_cache.ttl_seconds != max(ttl_seconds, 1)
    ):
        _metrics_payload_cache = _MetricsPayloadCache(ttl_seconds=max(ttl_seconds, 1))
    return _metrics_payload_cache.get_or_build(operations_service)
