"""Simple MCP‑like server to expose skills over HTTP.

This module implements a minimal FastAPI application that exposes
selected skill functions as HTTP endpoints. While it does not fully
implement the Model Context Protocol (MCP), it provides a similar
interface whereby remote callers can invoke individual skills by
name and supply parameters.

The server defines a single route ``/call_skill/{skill_name}`` that
takes JSON payloads and dispatches to the appropriate skill in
``src.skills``. Because this server lives inside your service
infrastructure, it enables local or remote agents to reuse the same
skills without direct imports.

Usage:

.. code-block:: bash

    uvicorn src.mcp.server:app --port 8001

This will start a server listening on port 8001 that can handle
requests like::

    POST /call_skill/classify_document
    {
        "text": "..."
    }

If the specified skill does not exist or required parameters are
missing, the server returns an HTTP 400 error.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any, Callable, Dict

from src import skills

app = FastAPI(title="MCP‑like Skills Server", version="0.1")


class SkillRequest(BaseModel):
    # Generic payload; fields vary by skill
    params: Dict[str, Any]


def _get_skill_function(name: str) -> Callable[..., Any]:
    """Resolve a skill function by name from ``src.skills``.

    :param name: the name of the skill function
    :returns: the callable
    :raises: HTTPException if function is not found
    """
    try:
        func: Callable[..., Any] = getattr(skills, name)
    except AttributeError:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    return func


@app.post("/call_skill/{skill_name}")
async def call_skill(skill_name: str, request: SkillRequest) -> Any:
    """Invoke a named skill with provided parameters.

    This endpoint expects a JSON body containing a single top‑level
    object with a ``params`` field mapping argument names to values.
    The skill function will be called with these keyword arguments.
    Unknown skills or wrong parameters will result in HTTP 400.

    :param skill_name: name of the skill to invoke
    :param request: body with parameters for the skill
    :returns: result of the skill invocation
    """
    func = _get_skill_function(skill_name)
    try:
        result = func(**request.params)
    except TypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"result": result}