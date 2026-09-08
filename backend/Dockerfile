FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/usr/local
WORKDIR /backend

COPY pyproject.toml uv.lock ./
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
# Test dependencies are included so the dev stack can run `pytest` inside the
# container (see docker-compose.dev.yml).
RUN uv sync --locked --extra test

COPY src ./src
