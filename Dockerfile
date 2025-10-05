# syntax=docker/dockerfile:1

# Use a slim Python base
ARG PYTHON_VERSION=3.12.11
FROM python:${PYTHON_VERSION}-slim AS base

# ---------------------------
#  Environment configuration
# ---------------------------
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Let uv / Python binaries from the venv be first on PATH
ENV PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# ---------------------------
#  System dependencies
# ---------------------------
# Install minimal build tools (asyncpg sometimes needs libpq)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc curl bash && \
    rm -rf /var/lib/apt/lists/*

# ---------------------------
#  Install uv and dependencies
# ---------------------------
RUN pip install --no-cache-dir uv

# Copy dependency files first for better caching
COPY pyproject.toml uv.lock ./

# Sync dependencies without caching or re-downloading
RUN uv sync --frozen --no-cache

# ---------------------------
#  Copy application code
# ---------------------------
COPY . .

# Ensure startup script is executable
RUN chmod +x /app/script.sh

# ---------------------------
#  Expose FastAPI port
# ---------------------------
EXPOSE 8000

# ---------------------------
#  Entrypoint
# ---------------------------
CMD ["/bin/bash", "/app/script.sh"]
