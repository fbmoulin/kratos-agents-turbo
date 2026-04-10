"""Structured logging helpers."""

from __future__ import annotations

import logging


class ContextFilter(logging.Filter):
    """Guarantee correlation fields exist on every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "task_id"):
            record.task_id = "-"
        if not hasattr(record, "session_id"):
            record.session_id = "-"
        return True


def configure_logging(level: str) -> None:
    """Configure root logging once per process."""

    root_logger = logging.getLogger()
    if getattr(root_logger, "_kratos_configured", False):
        return

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=(
            "%(asctime)s %(levelname)s %(name)s "
            "%(message)s task_id=%(task_id)s session_id=%(session_id)s"
        ),
    )
    context_filter = ContextFilter()
    for handler in root_logger.handlers:
        handler.addFilter(context_filter)
    root_logger._kratos_configured = True  # type: ignore[attr-defined]


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
