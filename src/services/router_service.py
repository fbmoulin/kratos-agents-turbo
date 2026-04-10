"""Agent routing rules."""

from __future__ import annotations

from src.agent import AgentRegistry
from src.core import NotFoundError, get_settings


class RouterService:
    """Resolve the target agent for a task."""

    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry
        self.settings = get_settings()

    def resolve_agent_id(
        self,
        *,
        requested_agent_id: str | None,
        task_type: str,
    ) -> str:
        if requested_agent_id:
            definition = self.registry.get(requested_agent_id)
            supported_types = definition.config.get("supported_task_types", [])
            if supported_types and task_type not in supported_types:
                raise NotFoundError(
                    f"Agent '{requested_agent_id}' does not support task_type '{task_type}'"
                )
            return definition.id

        for definition in self.registry.list():
            supported_types = definition.config.get("supported_task_types", [])
            if task_type in supported_types:
                return definition.id

        return self.settings.default_agent_id
