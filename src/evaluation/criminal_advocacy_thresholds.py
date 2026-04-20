from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_thresholds(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_report_against_thresholds(
    report: dict[str, Any],
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    failures: list[str] = []
    summary = dict(report.get("summary") or {})
    piece_types = set(report.get("piece_types") or [])
    required_piece_types = set(thresholds.get("required_piece_types") or [])
    missing_piece_types = sorted(required_piece_types - piece_types)
    if missing_piece_types:
        failures.append(
            "missing required piece types: " + ", ".join(missing_piece_types)
        )

    for metric, minimum in dict(thresholds.get("summary_minimums") or {}).items():
        observed = float(summary.get(metric) or 0.0)
        if observed < float(minimum):
            failures.append(
                f"summary metric '{metric}' below threshold: observed={observed:.3f} minimum={float(minimum):.3f}"
            )

    by_piece_type = dict(summary.get("by_piece_type") or {})
    for piece_type, minimums in dict(thresholds.get("per_piece_type_minimums") or {}).items():
        payload = by_piece_type.get(piece_type)
        if payload is None:
            failures.append(f"missing aggregate entry for piece type '{piece_type}'")
            continue
        for metric, minimum in dict(minimums).items():
            observed = float(payload.get(metric) or 0.0)
            if observed < float(minimum):
                failures.append(
                    f"piece type '{piece_type}' metric '{metric}' below threshold: "
                    f"observed={observed:.3f} minimum={float(minimum):.3f}"
                )

    return {
        "passed": not failures,
        "dataset_id": report.get("dataset_id"),
        "threshold_dataset_id": thresholds.get("dataset_id"),
        "failure_count": len(failures),
        "failures": failures,
    }
