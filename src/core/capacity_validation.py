"""Helpers for batch MVP capacity validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import mean
from typing import Any

DEFAULT_MESSAGES = {
    "despacho": "Gerar despacho padronizado de intimação para manifestação.",
    "decisao": "Gerar decisão padronizada com fundamentação objetiva e revisável.",
}


@dataclass(frozen=True)
class CapacityScenario:
    task_type: str
    count: int
    message: str


def default_scenarios() -> list[CapacityScenario]:
    return [
        CapacityScenario(
            task_type="despacho",
            count=50,
            message=DEFAULT_MESSAGES["despacho"],
        ),
        CapacityScenario(
            task_type="decisao",
            count=20,
            message=DEFAULT_MESSAGES["decisao"],
        ),
    ]


def parse_scenario(spec: str) -> CapacityScenario:
    task_type, separator, count_value = spec.partition("=")
    if separator != "=":
        raise ValueError("Scenario must follow the format '<task_type>=<count>'")
    task_type = task_type.strip().lower()
    if task_type not in DEFAULT_MESSAGES:
        raise ValueError("task_type must be 'despacho' or 'decisao'")
    try:
        count = int(count_value)
    except ValueError as exc:
        raise ValueError("Scenario count must be an integer") from exc
    if count <= 0:
        raise ValueError("Scenario count must be greater than zero")
    return CapacityScenario(task_type=task_type, count=count, message=DEFAULT_MESSAGES[task_type])


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def percentile(values: list[float], target: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    rank = (len(ordered) - 1) * target
    lower_index = int(rank)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    lower_value = ordered[lower_index]
    upper_value = ordered[upper_index]
    weight = rank - lower_index
    return lower_value + ((upper_value - lower_value) * weight)


def build_task_duration_stats(tasks: list[dict[str, Any]]) -> dict[str, float]:
    durations: list[float] = []
    for task in tasks:
        started_at = parse_timestamp(task.get("started_at"))
        finished_at = parse_timestamp(task.get("finished_at"))
        if started_at is None or finished_at is None:
            continue
        durations.append((finished_at - started_at).total_seconds())

    if not durations:
        return {
            "avg_seconds": 0.0,
            "p95_seconds": 0.0,
            "max_seconds": 0.0,
        }

    return {
        "avg_seconds": round(mean(durations), 3),
        "p95_seconds": round(percentile(durations, 0.95), 3),
        "max_seconds": round(max(durations), 3),
    }


def build_status_counts(tasks: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "queued": 0,
        "running": 0,
        "completed": 0,
        "failed": 0,
        "cancelled": 0,
    }
    for task in tasks:
        status = str(task.get("status") or "")
        if status in counts:
            counts[status] += 1
    return counts
