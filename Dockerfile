FROM node:22-slim AS frontend

RUN corepack enable && corepack prepare pnpm@10.32.1 --activate
WORKDIR /app/frontend
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM ghcr.io/astral-sh/uv:0.12.1 AS uv

FROM python:3.12-slim AS backend-build

COPY --from=uv /uv /uvx /bin/
WORKDIR /app
RUN apt-get update \
    && apt-get install --yes --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app
COPY --from=backend-build /app/.venv ./.venv
COPY api.py workflow_client.py ./
COPY --from=frontend /app/static ./static

EXPOSE 10000
CMD ["sh", "-c", "uvicorn api:api --host 0.0.0.0 --port ${PORT:-10000}"]
