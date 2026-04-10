from __future__ import annotations

from unittest.mock import Mock

import pytest

from src.core import ValidationError
from src.services.session_service import SessionService


def test_create_or_load_session_accepts_same_task_and_agent():
    session_manager = Mock()
    session_manager.load_session.return_value = {
        "id": "session-1",
        "task_id": "task-1",
        "agent_id": "agent-1",
        "status": "queued",
    }
    service = SessionService(session_manager=session_manager)

    session = service.create_or_load_session(
        task_id="task-1",
        agent_id="agent-1",
        requested_session_id="session-1",
    )

    assert session["id"] == "session-1"
    session_manager.create_session.assert_not_called()


def test_create_or_load_session_rejects_cross_task_rebind():
    session_manager = Mock()
    session_manager.load_session.return_value = {
        "id": "session-1",
        "task_id": "task-2",
        "agent_id": "agent-1",
        "status": "queued",
    }
    service = SessionService(session_manager=session_manager)

    with pytest.raises(ValidationError, match="does not belong to the current task"):
        service.create_or_load_session(
            task_id="task-1",
            agent_id="agent-1",
            requested_session_id="session-1",
        )


def test_create_or_load_session_rejects_mismatched_agent():
    session_manager = Mock()
    session_manager.load_session.return_value = {
        "id": "session-1",
        "task_id": "task-1",
        "agent_id": "agent-2",
        "status": "queued",
    }
    service = SessionService(session_manager=session_manager)

    with pytest.raises(ValidationError, match="belongs to a different agent"):
        service.create_or_load_session(
            task_id="task-1",
            agent_id="agent-1",
            requested_session_id="session-1",
        )
