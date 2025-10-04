# syntax=docker/dockerfile:1

# Base image
ARG PYTHON_VERSION=3.12.11
FROM python:${PYTHON_VERSION}-slim AS base

# Prevent Python from writing .pyc files and buffer logs
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Working directory
WORKDIR /app

# Install required system dependencies
RUN apt-get update && apt-get install -y curl git && rm -rf /var/lib/apt/lists/*

# Install uv (modern Python package manager & runner)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Copy dependency files first for better caching
COPY pyproject.toml uv.lock ./

# Install dependencies (locked versions)
RUN uv sync --frozen --no-dev

# Copy the rest of your source code
COPY . .

COPY .env .env

# Create a non-root user with a valid home directory
ARG UID=10001
RUN useradd -m -u "${UID}" appuser

# Switch to non-root user
USER appuser

# Set HOME explicitly (helps uv, FastAPI, etc.)
ENV HOME=/home/appuser

# Expose FastAPI default port
EXPOSE 8000

# Run your FastAPI app via uv
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
