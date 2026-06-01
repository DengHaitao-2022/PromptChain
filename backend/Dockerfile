# syntax=docker/dockerfile:1

FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:${PATH}" \
    UV_NO_CACHE=1 \
    API_HOST=0.0.0.0 \
    API_PORT=8000

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
ARG BACKEND_EXTRAS=""
RUN if [ -n "${BACKEND_EXTRAS}" ]; then \
        uv sync --frozen --no-dev --no-install-project --extra "${BACKEND_EXTRAS}"; \
    else \
        uv sync --frozen --no-dev --no-install-project; \
    fi

COPY backend/app.py backend/main.py ./
COPY backend/alembic.ini ./alembic.ini
COPY backend/alembic ./alembic
COPY backend/core ./core
COPY backend/db ./db
COPY backend/graph ./graph
COPY backend/models ./models
COPY backend/nodes ./nodes
COPY backend/orm ./orm
COPY backend/routes ./routes
COPY backend/services ./services

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:${API_PORT}/ || exit 1

CMD ["sh", "-c", "exec uvicorn app:app --host ${API_HOST} --port ${API_PORT}"]
