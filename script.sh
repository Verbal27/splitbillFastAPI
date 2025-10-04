#!/usr/bin/env bash
set -e  # exit immediately on error

echo "🔄 Running Alembic migrations..."

# Ensure alembic.ini exists
if [ ! -f "alembic.ini" ]; then
    echo "❌ ERROR: alembic.ini not found in $(pwd)"
    exit 1
fi

# Run migrations
uv run alembic upgrade head

echo "✅ Migrations complete. Starting FastAPI..."

# Start FastAPI (use uvicorn via uv)
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'
