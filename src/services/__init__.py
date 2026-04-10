"""Service composition helpers."""

from __future__ import annotations

from dataclasses import dataclass

from src.agent import get_agent_registry
from src.events import EventStore
from src.session import SessionManager
from src.services.orchestrator_service import OrchestratorService
from src.services.router_service import RouterService
from src.services.session_service import SessionService
from src.services.validator_service import ValidatorService


@dataclass(frozen=True)
class PlatformServices:
    validator_service: ValidatorService
    router_service: RouterService
    session_service: SessionService
    event_store: EventStore
    orchestrator_service: OrchestratorService


def create_platform_services() -> PlatformServices:
    registry = get_agent_registry()
    event_store = EventStore()
    session_manager = SessionManager()
    session_service = SessionService(session_manager=session_manager)
    router_service = RouterService(registry=registry)
    validator_service = ValidatorService()
    orchestrator_service = OrchestratorService(
        registry=registry,
        router_service=router_service,
        session_service=session_service,
        event_store=event_store,
    )
    return PlatformServices(
        validator_service=validator_service,
        router_service=router_service,
        session_service=session_service,
        event_store=event_store,
        orchestrator_service=orchestrator_service,
    )


__all__ = [
    "OrchestratorService",
    "PlatformServices",
    "RouterService",
    "SessionService",
    "ValidatorService",
    "create_platform_services",
]
