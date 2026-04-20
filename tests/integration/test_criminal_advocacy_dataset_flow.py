from __future__ import annotations

from fastapi.testclient import TestClient
from src.api.main import app
from src.api.main import services as api_services
from src.evaluation.criminal_advocacy_dataset import (
    build_case_pdf_bytes,
    build_runtime_message,
    iter_cases,
)
from src.worker.tasks import process_document_task


def test_criminal_advocacy_dataset_cases_complete_through_runtime(monkeypatch):
    monkeypatch.setattr("src.api.main.services.dispatch_service.publish", lambda **kwargs: None)

    client = TestClient(app, raise_server_exceptions=False)
    selected_cases = []
    covered_piece_types: set[str] = set()
    for case in iter_cases():
        if case.target_piece_type in covered_piece_types:
            continue
        selected_cases.append(case)
        covered_piece_types.add(case.target_piece_type)
        if len(covered_piece_types) == 4:
            break

    for case in selected_cases:
        response = client.post(
            "/tasks",
            files={
                "file": (
                    f"{case.case_id}.pdf",
                    build_case_pdf_bytes(case),
                    "application/pdf",
                )
            },
            data={
                "message": build_runtime_message(case),
                "tipo": case.runtime_task_type,
                "priority": "1",
            },
        )

        assert response.status_code == 200
        payload = response.json()
        task_id = payload["task_id"]
        task = api_services.task_service.get_task(task_id)
        staged_path = task["input_metadata"]["staged_path"]

        result = process_document_task.apply(
            kwargs={
                "task_id": task_id,
                "staged_path": staged_path,
                "file_name": f"{case.case_id}.pdf",
                "message": build_runtime_message(case),
                "task_type": case.runtime_task_type,
                "priority": 1,
                "requested_agent_id": None,
                "requested_session_id": None,
                "content_type": "application/pdf",
                "batch_id": None,
            }
        ).get()

        assert result["status"] == "completed"
        final_task = api_services.task_service.get_task(task_id)
        assert final_task["status"] == "completed"
        assert final_task["session_id"] is not None
        assert case.target_piece_type in final_task["result"]

        metadata = final_task["output_metadata"]
        assert metadata["agent_id"] in {
            "legal-despacho-agent",
            "legal-decisao-agent",
        }
        assert int(metadata["extracted_characters"]) > 0

        event_types = [
            event["event_type"]
            for event in api_services.task_service.list_events(task_id)
        ]
        assert "TASK_CREATED" in event_types
        assert "TASK_DISPATCHED" in event_types
        assert "TASK_STARTED" in event_types
        assert "TASK_COMPLETED" in event_types
