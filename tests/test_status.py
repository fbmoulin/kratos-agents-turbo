from __future__ import annotations

import pytest

from src.core import InvalidStateTransition, ensure_session_transition, ensure_task_transition


def test_task_state_machine_accepts_valid_transitions():
    ensure_task_transition("queued", "running")
    ensure_task_transition("running", "completed")
    ensure_task_transition("running", "failed")
    ensure_task_transition("running", "cancelled")


def test_task_state_machine_rejects_terminal_reentry():
    with pytest.raises(InvalidStateTransition):
        ensure_task_transition("completed", "running")

    with pytest.raises(InvalidStateTransition):
        ensure_task_transition("failed", "completed")


def test_session_state_machine_accepts_valid_transitions():
    ensure_session_transition("queued", "running")
    ensure_session_transition("running", "completed")
    ensure_session_transition("running", "failed")
    ensure_session_transition("running", "cancelled")


def test_session_state_machine_rejects_terminal_reentry():
    with pytest.raises(InvalidStateTransition):
        ensure_session_transition("completed", "running")

    with pytest.raises(InvalidStateTransition):
        ensure_session_transition("cancelled", "completed")
