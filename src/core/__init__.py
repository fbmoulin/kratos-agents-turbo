"""Core application primitives."""

from src.core.capacity_validation import (
    CapacityScenario,
    build_status_counts,
    build_task_duration_stats,
    default_scenarios,
    parse_scenario,
)
from src.core.exceptions import (
    ApplicationError,
    InvalidStateTransition,
    NotFoundError,
    PersistenceError,
    TransientTaskError,
    ValidationError,
)
from src.core.logging import configure_logging, get_logger
from src.core.retry import compute_retry_delay, is_retryable_exception
from src.core.settings import Settings, get_settings
from src.core.status import (
    TERMINAL_SESSION_STATUSES,
    TERMINAL_TASK_STATUSES,
    SessionStatus,
    TaskStatus,
    ensure_session_transition,
    ensure_task_transition,
)

__all__ = [
    "ApplicationError",
    "CapacityScenario",
    "InvalidStateTransition",
    "NotFoundError",
    "PersistenceError",
    "SessionStatus",
    "Settings",
    "TERMINAL_SESSION_STATUSES",
    "TERMINAL_TASK_STATUSES",
    "TaskStatus",
    "TransientTaskError",
    "ValidationError",
    "build_status_counts",
    "build_task_duration_stats",
    "compute_retry_delay",
    "configure_logging",
    "default_scenarios",
    "ensure_session_transition",
    "ensure_task_transition",
    "get_logger",
    "get_settings",
    "is_retryable_exception",
    "parse_scenario",
]
