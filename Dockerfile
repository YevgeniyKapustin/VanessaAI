# syntax=docker/dockerfile:1

FROM python:3.12-slim

ENV POETRY_VERSION=2.1.1 \
    POETRY_HOME="/opt/poetry" \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    PATH="/opt/poetry/bin:$PATH" \
    HF_HOME=/app/.cache/huggingface \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=0

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    libpq-dev \
    && curl -sSL https://install.python-poetry.org | python3 - \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml poetry.lock ./

RUN --mount=type=cache,target=/root/.cache/pip \
    poetry install --no-root --only main

RUN --mount=type=cache,target=/root/.cache/huggingface \
    python -c "from sentence_transformers import SentenceTransformer; \
SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

COPY app/ ./app/
COPY config/ ./config/
COPY alembic/ ./alembic/
COPY alembic.ini .

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
