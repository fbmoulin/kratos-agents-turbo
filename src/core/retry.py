"""Retry classification and backoff helpers."""

from __future__ import annotations

from src.core.exceptions import PersistenceError, TransientTaskError

RETRYABLE_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    PersistenceError,
    TransientTaskError,
)


def is_retryable_exception(exc: Exception) -> bool:
    """Return whether the exception should trigger a worker retry."""

    return isinstance(exc, RETRYABLE_EXCEPTIONS)


def compute_retry_delay(
    *,
    attempt: int,
    base_seconds: int,
    max_seconds: int,
) -> int:
    """Return exponential backoff with a bounded ceiling."""

    delay = base_seconds * (2 ** max(attempt, 0))
    return min(delay, max_seconds)
