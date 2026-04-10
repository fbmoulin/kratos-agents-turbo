"""Application-specific exceptions."""

from __future__ import annotations


class ApplicationError(Exception):
    """Base exception for domain and service errors."""


class ValidationError(ApplicationError):
    """Raised when an input payload is invalid."""


class NotFoundError(ApplicationError):
    """Raised when an expected entity does not exist."""


class InvalidStateTransition(ApplicationError):
    """Raised when a task or session transition is not allowed."""


class PersistenceError(ApplicationError):
    """Raised when persistence operations fail."""
