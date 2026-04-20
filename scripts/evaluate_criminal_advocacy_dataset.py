from __future__ import annotations

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
)
from src.worker.tasks import process_document_task


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
    return parser.parse_args()


def should_include(case, piece_types: set[str] | None) -> bool:
    return piece_types is None or case.target_piece_type in piece_types


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
    return {
        "case_id": case.case_id,
        "target_piece_type": case.target_piece_type,
        "runtime_task_type": case.runtime_task_type,
        "task_id": task_id,
        "status": final_task["status"],
        "classification": metadata.get("classification"),
        "extracted_characters": metadata.get("extracted_characters"),
        "event_types": [event["event_type"] for event in events],
        "contains_piece_type_hint": case.target_piece_type in output_text,
        "contains_strategy_hint": "Direção estratégica esperada" in output_text,
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
        "completed_cases": sum(1 for item in report_cases if item["status"] == "completed"),
        "piece_types": sorted({item["target_piece_type"] for item in report_cases}),
        "cases": report_cases,
    }

    report_text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(report_text, encoding="utf-8")
    else:
        print(report_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
