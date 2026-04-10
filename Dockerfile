FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN useradd --create-home --shell /bin/bash appuser

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY src ./src
COPY infra ./infra
COPY README.md ./

USER appuser

EXPOSE 8000 8001

CMD ["sh", "-c", "uvicorn src.api.main:app --host ${API_HOST:-0.0.0.0} --port ${API_PORT:-8000}"]
