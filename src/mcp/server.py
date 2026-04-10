"""Minimal MCP-style skill server."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from src import skills
from src.core import configure_logging, get_settings

settings = get_settings()
configure_logging(settings.log_level)
app = FastAPI(title="Kratos Agents Turbo MCP", version=settings.service_version)


class SkillRequest(BaseModel):
    params: dict[str, Any]


def _get_skill_function(name: str) -> Callable[..., Any]:
    try:
        return getattr(skills, name)
    except AttributeError as exc:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found") from exc


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "kratos-agents-turbo-mcp",
        "version": settings.service_version,
    }


@app.post("/call_skill/{skill_name}")
async def call_skill(skill_name: str, request: SkillRequest) -> dict[str, Any]:
    skill = _get_skill_function(skill_name)
    try:
        result = skill(**request.params)
    except TypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"result": result}
