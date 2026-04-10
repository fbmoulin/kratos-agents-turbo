from __future__ import annotations

import pytest
from src.core import InvalidStateTransition, NotFoundError
from src.services.task_service import TaskService


def test_task_service_mark_running_accepts_valid_transition(monkeypatch):
    service = TaskService()
    monkeypatch.setattr(
        "src.services.task_service.db.get_task",
        lambda task_id: {"id": task_id, "status": "queued"},
    )
    monkeypatch.setattr(
        "src.services.task_service.db.update_task",
        lambda task_id, **fields: {"id": task_id, **fields},
    )
    monkeypatch.setattr("src.services.task_service.db.utc_now", lambda: "now")

    task = service.mark_running("task-1", agent_id="agent-1", session_id="session-1")

    assert task["status"] == "running"
    assert task["agent_id"] == "agent-1"
    assert task["session_id"] == "session-1"


def test_task_service_rejects_invalid_terminal_transition(monkeypatch):
    service = TaskService()
    monkeypatch.setattr(
        "src.services.task_service.db.get_task",
        lambda task_id: {"id": task_id, "status": "completed"},
    )

    with pytest.raises(InvalidStateTransition):
        service.mark_failed("task-1", error="boom")


def test_task_service_list_events_requires_existing_task(monkeypatch):
    service = TaskService()
    monkeypatch.setattr("src.services.task_service.db.get_task", lambda task_id: None)

    with pytest.raises(NotFoundError):
        service.list_events("task-1")
