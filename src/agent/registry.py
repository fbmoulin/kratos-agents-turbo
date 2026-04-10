"""Declarative agent registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import yaml

from src.agent.legal_agent import LegalAgent
from src.core import NotFoundError, get_settings


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
        self._definitions = {
            raw_item["id"]: AgentDefinition(**raw_item)
            for raw_item in raw_catalog.get("agents", [])
        }
        self._implementations = {
            "legal_agent": LegalAgent,
        }

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
