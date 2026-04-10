from __future__ import annotations

from src.core import (
    PersistenceError,
    TransientTaskError,
    compute_retry_delay,
    is_retryable_exception,
)


def test_compute_retry_delay_uses_bounded_exponential_backoff():
    assert compute_retry_delay(attempt=0, base_seconds=30, max_seconds=600) == 30
    assert compute_retry_delay(attempt=1, base_seconds=30, max_seconds=600) == 60
    assert compute_retry_delay(attempt=4, base_seconds=30, max_seconds=600) == 480
    assert compute_retry_delay(attempt=6, base_seconds=30, max_seconds=600) == 600


def test_is_retryable_exception_matches_transient_failures():
    assert is_retryable_exception(TransientTaskError("retry me")) is True
    assert is_retryable_exception(PersistenceError("db offline")) is True
    assert is_retryable_exception(ConnectionError("socket")) is True
    assert is_retryable_exception(TimeoutError("slow")) is True
    assert is_retryable_exception(ValueError("bad input")) is False
