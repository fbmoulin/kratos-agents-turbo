from __future__ import annotations

from types import SimpleNamespace

from src.services.router_service import RouterService


def test_router_prefers_more_specific_agent_for_task_type(monkeypatch):
    registry = SimpleNamespace(
        get=lambda agent_id: None,
        list=lambda: [
            SimpleNamespace(
                id="legal-document-agent",
                config={"supported_task_types": ["despacho", "decisao", "sentenca"]},
            ),
            SimpleNamespace(
                id="legal-despacho-agent", config={"supported_task_types": ["despacho"]}
            ),
        ],
    )
    monkeypatch.setattr(
        "src.services.router_service.get_settings",
        lambda: SimpleNamespace(default_agent_id="legal-document-agent"),
    )

    service = RouterService(registry=registry)

    resolved = service.resolve_agent_id(requested_agent_id=None, task_type="despacho")

    assert resolved == "legal-despacho-agent"
