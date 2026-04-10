from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from src.agent.registry import AgentRegistry
from src.core import ValidationError


def _write_catalog(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_agent_registry_rejects_empty_catalog(tmp_path, monkeypatch):
    catalog = _write_catalog(tmp_path / "agents.yaml", "agents: []\n")
    monkeypatch.setattr(
        "src.agent.registry.get_settings",
        lambda: SimpleNamespace(catalog_path=catalog),
    )

    with pytest.raises(ValidationError, match="'agents' must be a non-empty list"):
        AgentRegistry()


def test_agent_registry_rejects_duplicate_agent_ids(tmp_path, monkeypatch):
    catalog = _write_catalog(
        tmp_path / "agents.yaml",
        """
agents:
  - id: a1
    name: A1
    implementation: legal_agent
    system_prompt: x
    config: {execution_mode: document}
  - id: a1
    name: A2
    implementation: legal_agent
    system_prompt: y
    config: {execution_mode: document}
""".strip(),
    )
    monkeypatch.setattr(
        "src.agent.registry.get_settings",
        lambda: SimpleNamespace(catalog_path=catalog),
    )

    with pytest.raises(ValidationError, match="duplicate agent id 'a1'"):
        AgentRegistry()


def test_agent_registry_rejects_unknown_implementation(tmp_path, monkeypatch):
    catalog = _write_catalog(
        tmp_path / "agents.yaml",
        """
agents:
  - id: a1
    name: A1
    implementation: missing_impl
    system_prompt: x
    config: {execution_mode: document}
""".strip(),
    )
    monkeypatch.setattr(
        "src.agent.registry.get_settings",
        lambda: SimpleNamespace(catalog_path=catalog),
    )

    with pytest.raises(ValidationError, match="unknown implementation 'missing_impl'"):
        AgentRegistry()


def test_agent_registry_rejects_malformed_supported_task_types(tmp_path, monkeypatch):
    catalog = _write_catalog(
        tmp_path / "agents.yaml",
        """
agents:
  - id: a1
    name: A1
    implementation: legal_agent
    system_prompt: x
    config:
      execution_mode: document
      supported_task_types: despacho
""".strip(),
    )
    monkeypatch.setattr(
        "src.agent.registry.get_settings",
        lambda: SimpleNamespace(catalog_path=catalog),
    )

    with pytest.raises(ValidationError, match="'supported_task_types' must be a list or tuple"):
        AgentRegistry()
