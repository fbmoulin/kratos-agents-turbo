"""Declarative agent registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import yaml

from src.agent.legal_agent import LegalAgent
from src.core import NotFoundError, ValidationError, get_settings


@dataclass(frozen=True)
class AgentDefinition:
    id: str
    name: str
    implementation: str
    system_prompt: str
    skills: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)


class AgentRegistry:
    """Loads agent definitions from a YAML catalog."""

    def __init__(self) -> None:
        settings = get_settings()
        with settings.catalog_path.open("r", encoding="utf-8") as file:
            raw_catalog = yaml.safe_load(file) or {}
        self._implementations = {
            "legal_agent": LegalAgent,
        }
        self._definitions = self._load_definitions(raw_catalog)

    def _load_definitions(self, raw_catalog: dict[str, Any]) -> dict[str, AgentDefinition]:
        raw_agents = raw_catalog.get("agents")
        if not isinstance(raw_agents, list) or not raw_agents:
            raise ValidationError("Agent catalog is invalid: 'agents' must be a non-empty list")

        definitions: dict[str, AgentDefinition] = {}
        for index, raw_item in enumerate(raw_agents, start=1):
            if not isinstance(raw_item, dict):
                raise ValidationError(
                    f"Agent catalog entry #{index} is invalid: expected a mapping"
                )
            agent_id = raw_item.get("id")
            if not agent_id or not isinstance(agent_id, str):
                raise ValidationError(
                    f"Agent catalog entry #{index} is invalid: 'id' must be a non-empty string"
                )
            if agent_id in definitions:
                raise ValidationError(f"Agent catalog is invalid: duplicate agent id '{agent_id}'")

            implementation = raw_item.get("implementation")
            if not implementation or not isinstance(implementation, str):
                raise ValidationError(
                    f"Agent '{agent_id}' is invalid: 'implementation' must be a non-empty string"
                )
            if implementation not in self._implementations:
                raise ValidationError(
                    f"Agent '{agent_id}' references unknown implementation '{implementation}'"
                )

            config = raw_item.get("config", {})
            if not isinstance(config, dict):
                raise ValidationError(f"Agent '{agent_id}' is invalid: 'config' must be a mapping")
            normalized_config = dict(config)
            if "execution_mode" not in normalized_config:
                normalized_config["execution_mode"] = "document"
            supported_task_types = normalized_config.get("supported_task_types")
            if supported_task_types is not None and not isinstance(
                supported_task_types, (list, tuple)
            ):
                raise ValidationError(
                    f"Agent '{agent_id}' is invalid: 'supported_task_types' must be a list or tuple"
                )

            normalized_item = {**raw_item, "config": normalized_config}
            definitions[agent_id] = AgentDefinition(**normalized_item)
        return definitions

    def get(self, agent_id: str) -> AgentDefinition:
        try:
            return self._definitions[agent_id]
        except KeyError as exc:
            raise NotFoundError(f"Agent '{agent_id}' is not registered") from exc

    def list(self) -> list[AgentDefinition]:
        return list(self._definitions.values())

    def build(self, agent_id: str) -> LegalAgent:
        definition = self.get(agent_id)
        try:
            implementation = self._implementations[definition.implementation]
        except KeyError as exc:
            raise NotFoundError(
                f"Agent implementation '{definition.implementation}' is not available"
            ) from exc
        return implementation(definition=definition)


@lru_cache(maxsize=1)
def get_agent_registry() -> AgentRegistry:
    return AgentRegistry()
