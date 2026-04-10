"""Celery application definition.

This module creates and configures a Celery application connected
to Redis. Celery is used to offload heavy processing of documents
to background workers so that the FastAPI web application remains
responsive while tasks are executed concurrently.

The broker and result backend URLs can be configured via environment
variables. By default Redis is used on ``redis://localhost:6379/0``
for the broker and ``redis://localhost:6379/1`` for the result
backend.
"""

import os
from celery import Celery

# Broker URL for Celery (points to Redis by default)
BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
BACKEND_URL = os.getenv("CELERY_BACKEND_URL", "redis://localhost:6379/1")


def create_celery_app() -> Celery:
    """Create and configure a Celery instance.

    :return: configured Celery app
    """
    app = Celery(
        "judicial_tasks",
        broker=BROKER_URL,
        backend=BACKEND_URL,
        include=["src.worker.tasks"],
    )
    # Set JSON serialisation for safety and interoperability
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
    )
    return app


# Global Celery app instance used by both the worker and API process
celery_app = create_celery_app()