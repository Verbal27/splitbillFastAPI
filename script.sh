#!/usr/bin/env bash
set -e

echo "⏳ Waiting for database to be ready..."

# Retry connection until it succeeds
until uv run python -c "import asyncpg, asyncio; asyncio.run(asyncpg.connect(
    user='${DB_USER}',
    password='${DB_PASS}',
    database='${DB_NAME}',
    host='${DB_HOST}',
    port=${DB_PORT}
))" >/dev/null 2>&1; do
    echo "   Database not ready yet, retrying in 2s..."
    sleep 2
done

echo "✅ Database is ready."

echo "🔄 Running Alembic migrations..."
uv run alembic upgrade head

echo "🚀 Starting FastAPI..."
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'
