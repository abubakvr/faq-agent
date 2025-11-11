# syntax=docker/dockerfile:1

# Multi-stage build to reduce final image size
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_ROOT_USER_ACTION=ignore

# Install minimal build dependencies (may be needed if some packages lack wheels)
# --prefer-binary flag will use pre-built wheels when available (much faster)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        libpq-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only requirements first to leverage layer cache
COPY requirements.txt ./

# Install Python dependencies (using Gemini direct API embeddings)
# BuildKit cache mount for pip cache - allows caching wheels between builds
# --prefer-binary: Use pre-built wheels instead of compiling from source (much faster)
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip setuptools wheel && \
    pip install --prefer-binary -r requirements.txt

# Final stage - minimal runtime image
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_ROOT_USER_ACTION=ignore

# Install only runtime dependencies (no build tools)
# libpq5 is needed at runtime for psycopg2-binary
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        libpq5 && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean

WORKDIR /app

# Copy Python packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy app code
COPY . .

# Expose FastAPI port
EXPOSE 8080

# Default envs can be overridden at runtime
ENV GEMINI_MODEL=${GEMINI_MODEL:-gemini-2.5-flash}

# Start server (main.py is now at src/main.py)
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080"]