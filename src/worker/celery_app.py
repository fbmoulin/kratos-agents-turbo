"""Celery application configuration."""

from __future__ import annotations

from celery import Celery

from src.core import configure_logging, get_settings
from src.core.observability import configure_celery_observability

settings = get_settings()
configure_logging(settings.log_level)
configure_celery_observability(settings)


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
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=settings.celery_worker_prefetch_multiplier,
        broker_transport_options={
            "visibility_timeout": settings.celery_visibility_timeout,
        },
        result_backend_transport_options={
            "visibility_timeout": settings.celery_visibility_timeout,
        },
    )
    return app


celery_app = create_celery_app()
