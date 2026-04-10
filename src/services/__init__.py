"""Service composition helpers."""

from __future__ import annotations

from dataclasses import dataclass

from src.agent import get_agent_registry
from src.core import get_settings
from src.events import EventStore
from src.services.batch_service import BatchService
from src.services.cancellation_service import CancellationService
from src.services.dispatch_service import DispatchService
from src.services.operations_service import OperationsService
from src.services.orchestrator_service import OrchestratorService
from src.services.router_service import RouterService
from src.services.session_service import SessionService
from src.services.staging_service import StagingService
from src.services.submission_service import SubmissionService
from src.services.task_service import TaskService
from src.services.validator_service import ValidatorService
from src.session import SessionManager


@dataclass(frozen=True)
class PlatformServices:
    batch_service: BatchService
    task_service: TaskService
    validator_service: ValidatorService
    router_service: RouterService
    session_service: SessionService
    staging_service: StagingService
    dispatch_service: DispatchService
    submission_service: SubmissionService
    cancellation_service: CancellationService
    operations_service: OperationsService
    event_store: EventStore
    orchestrator_service: OrchestratorService


def create_platform_services() -> PlatformServices:
    settings = get_settings()
    registry = get_agent_registry()
    event_store = EventStore()
    dispatch_service = DispatchService(event_store=event_store)
    session_manager = SessionManager()
    task_service = TaskService()
    batch_service = BatchService(task_service=task_service, event_store=event_store)
    operations_service = OperationsService(batch_service=batch_service)
    session_service = SessionService(session_manager=session_manager)
    router_service = RouterService(registry=registry)
    validator_service = ValidatorService()
    staging_service = StagingService()
    submission_service = SubmissionService(
        validator_service=validator_service,
        staging_service=staging_service,
        task_service=task_service,
        batch_service=batch_service,
        dispatch_service=dispatch_service,
        event_store=event_store,
        settings=settings,
    )
    cancellation_service = CancellationService(
        task_service=task_service,
        session_service=session_service,
        batch_service=batch_service,
        event_store=event_store,
    )
    orchestrator_service = OrchestratorService(
        registry=registry,
        task_service=task_service,
        router_service=router_service,
        session_service=session_service,
        event_store=event_store,
    )
    return PlatformServices(
        batch_service=batch_service,
        task_service=task_service,
        validator_service=validator_service,
        router_service=router_service,
        session_service=session_service,
        staging_service=staging_service,
        dispatch_service=dispatch_service,
        submission_service=submission_service,
        cancellation_service=cancellation_service,
        operations_service=operations_service,
        event_store=event_store,
        orchestrator_service=orchestrator_service,
    )


__all__ = [
    "BatchService",
    "CancellationService",
    "DispatchService",
    "OperationsService",
    "OrchestratorService",
    "PlatformServices",
    "RouterService",
    "SessionService",
    "StagingService",
    "SubmissionService",
    "TaskService",
    "ValidatorService",
    "create_platform_services",
]
