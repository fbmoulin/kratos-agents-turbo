"""Top level package for the judicial task processing application.

This package provides the FastAPI application, Celery tasks and
helpers to persist task state to Supabase-hosted PostgreSQL. It is intended
to be self‑contained so that you can run the API server, worker
processes and monitor tasks without requiring the original Node.js
infrastructure that ships with this repository.
"""

__all__ = []
