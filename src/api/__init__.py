"""API package exposing the FastAPI application.

The ``app`` object in ``main.py`` is the entry point to run the
HTTP server. Use ``uvicorn src.api.main:app`` to serve the API.
"""

__all__ = ["app"]