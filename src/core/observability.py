"""OpenTelemetry bootstrap helpers."""

from __future__ import annotations

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_NAMESPACE, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from src.core.settings import Settings

_provider_configured = False
_fastapi_instrumented = False
_celery_instrumented = False
_psycopg_instrumented = False
_redis_instrumented = False


def _configure_provider(settings: Settings) -> None:
    global _provider_configured
    if (
        _provider_configured
        or not settings.otel_enabled
        or not settings.otel_exporter_otlp_endpoint
    ):
        return

    resource = Resource.create(
        {
            SERVICE_NAME: settings.service_name,
            SERVICE_VERSION: settings.service_version,
            SERVICE_NAMESPACE: settings.otel_service_namespace,
        }
    )
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(
        endpoint=settings.otel_exporter_otlp_endpoint,
        headers=settings.otel_exporter_otlp_headers,
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _provider_configured = True


def configure_api_observability(app: FastAPI, settings: Settings) -> None:
    global _fastapi_instrumented, _psycopg_instrumented, _redis_instrumented
    _configure_provider(settings)
    if not settings.otel_enabled:
        return
    if not _fastapi_instrumented:
        FastAPIInstrumentor.instrument_app(app)
        _fastapi_instrumented = True
    if not _psycopg_instrumented:
        PsycopgInstrumentor().instrument()
        _psycopg_instrumented = True
    if not _redis_instrumented:
        RedisInstrumentor().instrument()
        _redis_instrumented = True


def configure_celery_observability(settings: Settings) -> None:
    global _celery_instrumented, _psycopg_instrumented, _redis_instrumented
    _configure_provider(settings)
    if not settings.otel_enabled:
        return
    if not _celery_instrumented:
        CeleryInstrumentor().instrument()
        _celery_instrumented = True
    if not _psycopg_instrumented:
        PsycopgInstrumentor().instrument()
        _psycopg_instrumented = True
    if not _redis_instrumented:
        RedisInstrumentor().instrument()
        _redis_instrumented = True
