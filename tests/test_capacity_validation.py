from __future__ import annotations

from src.core.capacity_validation import (
    build_status_counts,
    build_task_duration_stats,
    default_scenarios,
    parse_scenario,
)


def test_default_scenarios_match_mvp_targets():
    scenarios = default_scenarios()

    assert [(scenario.task_type, scenario.count) for scenario in scenarios] == [
        ("despacho", 50),
        ("decisao", 20),
    ]


def test_parse_scenario_accepts_valid_input():
    scenario = parse_scenario("despacho=12")

    assert scenario.task_type == "despacho"
    assert scenario.count == 12
    assert "intimação" in scenario.message


def test_parse_scenario_rejects_invalid_task_type():
    try:
        parse_scenario("sentenca=5")
    except ValueError as exc:
        assert "task_type" in str(exc)
    else:
        raise AssertionError("Expected ValueError for unsupported task_type")


def test_build_task_duration_stats_uses_started_and_finished_timestamps():
    stats = build_task_duration_stats(
        [
            {
                "started_at": "2026-04-10T10:00:00Z",
                "finished_at": "2026-04-10T10:00:03Z",
            },
            {
                "started_at": "2026-04-10T10:00:00Z",
                "finished_at": "2026-04-10T10:00:05Z",
            },
        ]
    )

    assert stats == {
        "avg_seconds": 4.0,
        "p95_seconds": 4.9,
        "max_seconds": 5.0,
    }


def test_build_status_counts_tracks_known_statuses():
    counts = build_status_counts(
        [
            {"status": "queued"},
            {"status": "completed"},
            {"status": "completed"},
            {"status": "failed"},
        ]
    )

    assert counts == {
        "queued": 1,
        "running": 0,
        "completed": 2,
        "failed": 1,
        "cancelled": 0,
    }
