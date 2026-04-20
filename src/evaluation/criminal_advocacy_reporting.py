from __future__ import annotations

from typing import Any


def _pct(value: float) -> str:
    return f"{round(value * 100, 1)}%"


def _score(value: float) -> str:
    return f"{value:.3f}"


def _top_missing(section: dict[str, Any], limit: int = 5) -> str:
    missing = list(section.get("missing") or [])
    if not missing:
        return "none"
    return ", ".join(missing[:limit])


def _recommendations(summary: dict[str, Any], cases: list[dict[str, Any]]) -> list[str]:
    recommendations: list[str] = []
    if float(summary.get("classification_match_rate") or 0.0) < 1.0:
        recommendations.append(
            "Review document classification prompts and extraction context before changing routing."
        )
    if float(summary.get("average_strategy_coverage") or 0.0) < 0.35:
        recommendations.append(
            "Strengthen strategic framing in generated drafts; the runtime is not carrying the expected defense direction into the final text."
        )
    if float(summary.get("average_tactical_coverage") or 0.0) < 0.35:
        recommendations.append(
            "Prioritize tactical checklist injection so requests, evidence gaps, and fallback asks appear explicitly in the output."
        )
    if float(summary.get("average_proof_gap_coverage") or 0.0) < 0.25:
        recommendations.append(
            "Improve handling of evidentiary weaknesses; the current drafts under-reference proof gaps from the dataset."
        )
    if any(case["scores"]["missing_required_events"] for case in cases):
        recommendations.append(
            "Inspect event persistence and worker orchestration for missing lifecycle events before trusting runtime observability."
        )
    if not recommendations:
        recommendations.append(
            "Current report shows no immediate structural blocker; proceed to larger runs and compare scores by piece type."
        )
    return recommendations


def render_markdown_report(report: dict[str, Any]) -> str:
    summary = dict(report.get("summary") or {})
    cases = list(report.get("cases") or [])
    by_piece_type = dict(summary.get("by_piece_type") or {})
    threshold_check = dict(report.get("threshold_check") or {})
    sorted_cases = sorted(
        cases,
        key=lambda item: float(item.get("scores", {}).get("overall_score") or 0.0),
    )
    weakest_cases = sorted_cases[: min(5, len(sorted_cases))]

    lines: list[str] = []
    lines.append("# Criminal Advocacy Evaluation Report")
    lines.append("")
    lines.append(f"- Dataset: `{report.get('dataset_id', '-')}`")
    lines.append(f"- Evaluated cases: `{report.get('evaluated_cases', 0)}`")
    lines.append(
        f"- Piece types: `{', '.join(report.get('piece_types') or []) or '-'}`"
    )
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| Completed cases | `{summary.get('completed_cases', 0)}` |")
    lines.append(f"| Completion rate | `{_pct(float(summary.get('completion_rate') or 0.0))}` |")
    lines.append(
        f"| Classification match rate | `{_pct(float(summary.get('classification_match_rate') or 0.0))}` |"
    )
    lines.append(
        f"| Piece-type hint rate | `{_pct(float(summary.get('piece_type_hint_rate') or 0.0))}` |"
    )
    lines.append(
        f"| Average overall score | `{_score(float(summary.get('average_overall_score') or 0.0))}` |"
    )
    lines.append(
        f"| Average strategy coverage | `{_score(float(summary.get('average_strategy_coverage') or 0.0))}` |"
    )
    lines.append(
        f"| Average tactical coverage | `{_score(float(summary.get('average_tactical_coverage') or 0.0))}` |"
    )
    lines.append(
        f"| Average proof-gap coverage | `{_score(float(summary.get('average_proof_gap_coverage') or 0.0))}` |"
    )
    lines.append(
        f"| Average risk coverage | `{_score(float(summary.get('average_risk_coverage') or 0.0))}` |"
    )
    lines.append("")

    if threshold_check:
        lines.append("## Threshold Gate")
        lines.append("")
        lines.append(
            f"- Status: `{'passed' if threshold_check.get('passed') else 'failed'}`"
        )
        lines.append(f"- Failure count: `{threshold_check.get('failure_count', 0)}`")
        if threshold_check.get("failures"):
            lines.append("- Failures:")
            for failure in threshold_check["failures"]:
                lines.append(f"  - {failure}")
        lines.append("")

    if by_piece_type:
        lines.append("## By Piece Type")
        lines.append("")
        lines.append("| Piece type | Cases | Completion rate | Avg overall score |")
        lines.append("| --- | --- | --- | --- |")
        for piece_type, payload in sorted(by_piece_type.items()):
            lines.append(
                f"| `{piece_type}` | `{payload.get('cases', 0)}` | "
                f"`{_pct(float(payload.get('completion_rate') or 0.0))}` | "
                f"`{_score(float(payload.get('average_overall_score') or 0.0))}` |"
            )
        lines.append("")

    lines.append("## Recommended Actions")
    lines.append("")
    for recommendation in _recommendations(summary, cases):
        lines.append(f"- {recommendation}")
    lines.append("")

    if weakest_cases:
        lines.append("## Weakest Cases")
        lines.append("")
        for case in weakest_cases:
            scores = case["scores"]
            lines.append(
                f"### `{case['case_id']}` — `{case['target_piece_type']}` — score `{_score(float(scores['overall_score']))}`"
            )
            lines.append(
                f"- Classification: expected `{scores['expected_runtime_classification']}`, got `{case.get('classification')}`"
            )
            lines.append(
                f"- Missing events: `{', '.join(scores['missing_required_events']) or 'none'}`"
            )
            lines.append(
                f"- Strategy missing keywords: `{_top_missing(scores['strategy_coverage'])}`"
            )
            lines.append(
                f"- Tactical missing keywords: `{_top_missing(scores['tactical_priorities_coverage'])}`"
            )
            lines.append(
                f"- Proof-gap missing keywords: `{_top_missing(scores['proof_gaps_coverage'])}`"
            )
            lines.append(
                f"- Risk missing keywords: `{_top_missing(scores['risks_coverage'])}`"
            )
            lines.append("")

    if cases:
        lines.append("## Case Matrix")
        lines.append("")
        lines.append("| Case | Piece type | Status | Classification | Overall score |")
        lines.append("| --- | --- | --- | --- | --- |")
        for case in sorted_cases:
            lines.append(
                f"| `{case['case_id']}` | `{case['target_piece_type']}` | `{case['status']}` | "
                f"`{case.get('classification')}` | `{_score(float(case['scores']['overall_score']))}` |"
            )
        lines.append("")

    return "\n".join(lines)
