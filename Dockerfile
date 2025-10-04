# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.12.11
FROM python:${PYTHON_VERSION}-slim AS base

# Environment setup
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Install uv globally
RUN pip install --no-cache-dir uv

# Copy project files
COPY uv.lock pyproject.toml ./

# Install dependencies into a venv inside /app
RUN uv sync --frozen --no-cache

# Copy the rest of the code and environment
COPY . .
COPY .env .env

# Expose the FastAPI port
EXPOSE 8000

COPY script.sh /app/script.sh
RUN chmod +x /app/script.sh

CMD ["bash", "/app/script.sh"]

