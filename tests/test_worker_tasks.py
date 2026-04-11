from __future__ import annotations

import pytest
from celery.exceptions import Ignore
from src.worker.tasks import process_document_task


def test_process_document_task_deletes_staged_input_on_success(monkeypatch):
    deleted_paths: list[str] = []
    updated_tasks: list[dict[str, object]] = []

    monkeypatch.setattr(process_document_task, "check_cancelled", lambda task_id: None)
    monkeypatch.setattr(
        "src.worker.tasks.services.staging_service.load_staged_input",
        lambda staged_path: b"%PDF-1.4 test",
    )
    monkeypatch.setattr(
        "src.worker.tasks.services.staging_service.delete_staged_input",
        lambda staged_path: deleted_paths.append(staged_path),
    )
    monkeypatch.setattr(
        "src.worker.tasks.services.orchestrator_service.execute",
        lambda **kwargs: {"task_id": kwargs["task_id"], "status": "completed"},
    )
    monkeypatch.setattr(
        "src.worker.tasks.db.get_task",
        lambda task_id: {
            "id": task_id,
            "input_metadata": {
                "staged_path": "/tmp/task-1.pdf",
                "content_type": "application/pdf",
            },
        },
    )
    monkeypatch.setattr(
        "src.worker.tasks.db.update_task",
        lambda task_id, **fields: updated_tasks.append({"task_id": task_id, **fields}),
    )

    result = process_document_task.run(
        task_id="task-1",
        staged_path="/tmp/task-1.pdf",
        file_name="task-1.pdf",
        message="Emitir minuta",
        task_type="despacho",
        priority=9,
    )

    assert result == {"task_id": "task-1", "status": "completed"}
    assert deleted_paths == ["/tmp/task-1.pdf"]
    assert updated_tasks[0]["task_id"] == "task-1"
    assert "staged_path" not in updated_tasks[0]["input_metadata"]
    assert updated_tasks[0]["input_metadata"]["staged_input_deleted"] is True
    assert updated_tasks[0]["input_metadata"]["content_type"] == "application/pdf"


def test_process_document_task_deletes_staged_input_on_terminal_failure(monkeypatch):
    deleted_paths: list[str] = []
    terminal_failures: list[dict[str, object]] = []
    updated_tasks: list[dict[str, object]] = []

    monkeypatch.setattr(process_document_task, "check_cancelled", lambda task_id: None)
    monkeypatch.setattr(
        "src.worker.tasks.services.staging_service.load_staged_input",
        lambda staged_path: b"%PDF-1.4 test",
    )
    monkeypatch.setattr(
        "src.worker.tasks.services.staging_service.delete_staged_input",
        lambda staged_path: deleted_paths.append(staged_path),
    )
    monkeypatch.setattr(
        "src.worker.tasks.services.orchestrator_service.execute",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr("src.worker.tasks.is_retryable_exception", lambda exc: False)
    monkeypatch.setattr(
        process_document_task,
        "mark_terminal_failure",
        lambda **kwargs: terminal_failures.append(kwargs),
    )
    monkeypatch.setattr(
        "src.worker.tasks.db.get_task",
        lambda task_id: {
            "id": task_id,
            "input_metadata": {
                "staged_path": "/tmp/task-2.pdf",
            },
        },
    )
    monkeypatch.setattr(
        "src.worker.tasks.db.update_task",
        lambda task_id, **fields: updated_tasks.append({"task_id": task_id, **fields}),
    )

    with pytest.raises(RuntimeError, match="boom"):
        process_document_task.run(
            task_id="task-2",
            staged_path="/tmp/task-2.pdf",
            file_name="task-2.pdf",
            message="Emitir minuta",
            task_type="despacho",
            priority=9,
        )

    assert deleted_paths == ["/tmp/task-2.pdf"]
    assert terminal_failures[0]["task_id"] == "task-2"
    assert updated_tasks[0]["task_id"] == "task-2"
    assert updated_tasks[0]["input_metadata"]["staged_input_deleted"] is True


def test_process_document_task_keeps_staged_input_when_retry_is_scheduled(monkeypatch):
    deleted_paths: list[str] = []
    updated_tasks: list[dict[str, object]] = []

    monkeypatch.setattr(process_document_task, "check_cancelled", lambda task_id: None)
    monkeypatch.setattr(
        "src.worker.tasks.services.staging_service.load_staged_input",
        lambda staged_path: b"%PDF-1.4 test",
    )
    monkeypatch.setattr(
        "src.worker.tasks.services.staging_service.delete_staged_input",
        lambda staged_path: deleted_paths.append(staged_path),
    )
    monkeypatch.setattr(
        "src.worker.tasks.services.orchestrator_service.execute",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("retryable")),
    )
    monkeypatch.setattr("src.worker.tasks.is_retryable_exception", lambda exc: True)

    class RetryScheduled(Exception):
        pass

    monkeypatch.setattr(
        process_document_task,
        "schedule_retry",
        lambda **kwargs: (_ for _ in ()).throw(RetryScheduled()),
    )
    monkeypatch.setattr(
        "src.worker.tasks.db.update_task",
        lambda task_id, **fields: updated_tasks.append({"task_id": task_id, **fields}),
    )

    with pytest.raises(RetryScheduled):
        process_document_task.run(
            task_id="task-3",
            staged_path="/tmp/task-3.pdf",
            file_name="task-3.pdf",
            message="Emitir minuta",
            task_type="despacho",
            priority=9,
        )

    assert deleted_paths == []
    assert updated_tasks == []


def test_process_document_task_deletes_staged_input_when_cancelled(monkeypatch):
    deleted_paths: list[str] = []
    updated_tasks: list[dict[str, object]] = []

    monkeypatch.setattr(
        process_document_task,
        "check_cancelled",
        lambda task_id: (_ for _ in ()).throw(Ignore("Task was cancelled")),
    )
    monkeypatch.setattr(
        "src.worker.tasks.services.staging_service.delete_staged_input",
        lambda staged_path: deleted_paths.append(staged_path),
    )
    monkeypatch.setattr(
        "src.worker.tasks.db.get_task",
        lambda task_id: {
            "id": task_id,
            "input_metadata": {
                "staged_path": "/tmp/task-4.pdf",
            },
        },
    )
    monkeypatch.setattr(
        "src.worker.tasks.db.update_task",
        lambda task_id, **fields: updated_tasks.append({"task_id": task_id, **fields}),
    )

    with pytest.raises(Ignore):
        process_document_task.run(
            task_id="task-4",
            staged_path="/tmp/task-4.pdf",
            file_name="task-4.pdf",
            message="Emitir minuta",
            task_type="despacho",
            priority=9,
        )

    assert deleted_paths == ["/tmp/task-4.pdf"]
    assert updated_tasks[0]["task_id"] == "task-4"
    assert updated_tasks[0]["input_metadata"]["staged_input_deleted"] is True
