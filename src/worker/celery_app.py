"""Celery application configuration."""

from __future__ import annotations

from celery import Celery

from src.core import configure_logging, get_settings

settings = get_settings()
configure_logging(settings.log_level)


def create_celery_app() -> Celery:
    app = Celery(
        "kratos_agents_turbo",
        broker=settings.celery_broker_url,
        backend=settings.celery_backend_url,
        include=["src.worker.tasks"],
    )
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_default_queue=settings.celery_task_queue,
        task_track_started=True,
        worker_send_task_events=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
    )
    return app


celery_app = create_celery_app()
