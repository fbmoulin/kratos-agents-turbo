from __future__ import annotations

# ruff: noqa: E402
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from src.api.main import app
from src.api.main import services as api_services
from src.evaluation.criminal_advocacy_dataset import (
    build_case_pdf_bytes,
    build_runtime_message,
    iter_cases,
    score_keyword_coverage,
)
from src.evaluation.criminal_advocacy_reporting import render_markdown_report
from src.evaluation.criminal_advocacy_thresholds import (
    evaluate_report_against_thresholds,
    load_thresholds,
)
from src.worker.tasks import process_document_task

DEFAULT_THRESHOLDS_PATH = (
    ROOT / "datasets" / "criminal_advocacy_stage2" / "thresholds.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the criminal advocacy Stage 2 dataset through the current runtime."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of cases to evaluate.",
    )
    parser.add_argument(
        "--piece-type",
        action="append",
        default=None,
        dest="piece_types",
        help="Filter by target piece type. Repeat to include more than one.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write the JSON report.",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=None,
        help="Optional path to write a Markdown review report.",
    )
    parser.add_argument(
        "--thresholds",
        type=Path,
        default=None,
        help=(
            "Optional path to evaluate the JSON report against threshold gates. "
            f"Recommended baseline: {DEFAULT_THRESHOLDS_PATH}"
        ),
    )
    return parser.parse_args()


def should_include(case, piece_types: set[str] | None) -> bool:
    return piece_types is None or case.target_piece_type in piece_types


def build_case_scores(
    case,
    *,
    output_text: str,
    status: str,
    classification,
    event_types: list[str],
):
    strategy = score_keyword_coverage(output_text, [case.expected_strategic_direction])
    tactical = score_keyword_coverage(output_text, case.notes["tactical_priorities"])
    proof_gaps = score_keyword_coverage(output_text, case.notes["proof_gaps"])
    risks = score_keyword_coverage(output_text, case.notes["risks"])
    required_events = {
        "TASK_CREATED",
        "TASK_DISPATCHED",
        "TASK_STARTED",
        "TASK_COMPLETED",
    }
    observed_events = set(event_types)
    missing_events = sorted(required_events - observed_events)
    classification_match = classification == case.expected_runtime_classification
    completed = status == "completed"
    piece_type_hint = case.target_piece_type in output_text
    score_components = [
        1.0 if completed else 0.0,
        1.0 if classification_match else 0.0,
        1.0 if piece_type_hint else 0.0,
        strategy["score"],
        tactical["score"],
        proof_gaps["score"],
        risks["score"],
        1.0 if not missing_events else 0.0,
    ]
    overall_score = round(sum(score_components) / len(score_components), 3)
    return {
        "completed": completed,
        "classification_match": classification_match,
        "expected_runtime_classification": case.expected_runtime_classification,
        "piece_type_hint_present": piece_type_hint,
        "strategy_coverage": strategy,
        "tactical_priorities_coverage": tactical,
        "proof_gaps_coverage": proof_gaps,
        "risks_coverage": risks,
        "missing_required_events": missing_events,
        "overall_score": overall_score,
    }


def aggregate_report(case_reports: list[dict[str, object]]) -> dict[str, object]:
    if not case_reports:
        return {
            "completed_cases": 0,
            "completion_rate": 0.0,
            "classification_match_rate": 0.0,
            "piece_type_hint_rate": 0.0,
            "average_overall_score": 0.0,
            "average_strategy_coverage": 0.0,
            "average_tactical_coverage": 0.0,
            "average_proof_gap_coverage": 0.0,
            "average_risk_coverage": 0.0,
            "by_piece_type": {},
        }

    def average(values: list[float]) -> float:
        return round(sum(values) / len(values), 3) if values else 0.0

    grouped: dict[str, list[dict[str, object]]] = {}
    for item in case_reports:
        grouped.setdefault(str(item["target_piece_type"]), []).append(item)

    by_piece_type: dict[str, object] = {}
    for piece_type, items in grouped.items():
        by_piece_type[piece_type] = {
            "cases": len(items),
            "average_overall_score": average(
                [float(item["scores"]["overall_score"]) for item in items]
            ),
            "completion_rate": average(
                [1.0 if item["scores"]["completed"] else 0.0 for item in items]
            ),
        }

    return {
        "completed_cases": sum(1 for item in case_reports if item["scores"]["completed"]),
        "completion_rate": average(
            [1.0 if item["scores"]["completed"] else 0.0 for item in case_reports]
        ),
        "classification_match_rate": average(
            [1.0 if item["scores"]["classification_match"] else 0.0 for item in case_reports]
        ),
        "piece_type_hint_rate": average(
            [1.0 if item["scores"]["piece_type_hint_present"] else 0.0 for item in case_reports]
        ),
        "average_overall_score": average(
            [float(item["scores"]["overall_score"]) for item in case_reports]
        ),
        "average_strategy_coverage": average(
            [float(item["scores"]["strategy_coverage"]["score"]) for item in case_reports]
        ),
        "average_tactical_coverage": average(
            [
                float(item["scores"]["tactical_priorities_coverage"]["score"])
                for item in case_reports
            ]
        ),
        "average_proof_gap_coverage": average(
            [float(item["scores"]["proof_gaps_coverage"]["score"]) for item in case_reports]
        ),
        "average_risk_coverage": average(
            [float(item["scores"]["risks_coverage"]["score"]) for item in case_reports]
        ),
        "by_piece_type": by_piece_type,
    }


def run_case(client: TestClient, case) -> dict[str, object]:
    pdf_bytes = build_case_pdf_bytes(case)
    message = build_runtime_message(case)

    response = client.post(
        "/tasks",
        files={"file": (f"{case.case_id}.pdf", pdf_bytes, "application/pdf")},
        data={"message": message, "tipo": case.runtime_task_type, "priority": "1"},
    )
    if response.status_code not in {200, 202}:
        raise RuntimeError(
            f"Case {case.case_id} failed during submission with status {response.status_code}: "
            f"{response.text}"
        )

    payload = response.json()
    task_id = payload["task_id"]
    task = api_services.task_service.get_task(task_id)
    staged_path = task["input_metadata"]["staged_path"]

    result = process_document_task.apply(
        kwargs={
            "task_id": task_id,
            "staged_path": staged_path,
            "file_name": f"{case.case_id}.pdf",
            "message": message,
            "task_type": case.runtime_task_type,
            "priority": 1,
            "requested_agent_id": None,
            "requested_session_id": None,
            "content_type": "application/pdf",
            "batch_id": None,
        }
    ).get()

    final_task = api_services.task_service.get_task(task_id)
    events = api_services.task_service.list_events(task_id)
    output_text = str(final_task.get("result") or result.get("result") or "")
    metadata = dict(final_task.get("output_metadata") or result.get("metadata") or {})
    event_types = [event["event_type"] for event in events]
    scores = build_case_scores(
        case,
        output_text=output_text,
        status=str(final_task["status"]),
        classification=metadata.get("classification"),
        event_types=event_types,
    )
    return {
        "case_id": case.case_id,
        "title": case.title,
        "target_piece_type": case.target_piece_type,
        "runtime_task_type": case.runtime_task_type,
        "task_id": task_id,
        "status": final_task["status"],
        "classification": metadata.get("classification"),
        "extracted_characters": metadata.get("extracted_characters"),
        "event_types": event_types,
        "output_excerpt": output_text[:400],
        "scores": scores,
    }


def main() -> int:
    if not (os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL")):
        print("DATABASE_URL or SUPABASE_DB_URL must be configured for the evaluation harness.")
        return 2

    args = parse_args()
    selected_piece_types = set(args.piece_types) if args.piece_types else None
    cases = [case for case in iter_cases() if should_include(case, selected_piece_types)]
    if args.limit is not None:
        cases = cases[: args.limit]

    original_publish = api_services.dispatch_service.publish
    api_services.dispatch_service.publish = lambda **kwargs: None
    try:
        client = TestClient(app, raise_server_exceptions=False)
        report_cases = [run_case(client, case) for case in cases]
    finally:
        api_services.dispatch_service.publish = original_publish

    report = {
        "dataset_id": "criminal-advocacy-stage2-v1",
        "evaluated_cases": len(report_cases),
        "piece_types": sorted({item["target_piece_type"] for item in report_cases}),
        "summary": aggregate_report(report_cases),
        "cases": report_cases,
    }
    if args.thresholds:
        thresholds = load_thresholds(args.thresholds)
        report["threshold_check"] = evaluate_report_against_thresholds(report, thresholds)

    report_text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(report_text, encoding="utf-8")
    else:
        print(report_text)
    if args.markdown_output:
        args.markdown_output.write_text(render_markdown_report(report), encoding="utf-8")
    if args.thresholds:
        return 0 if report["threshold_check"]["passed"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
