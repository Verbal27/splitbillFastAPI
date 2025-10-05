#!/usr/bin/env bash
set -e

echo "🚀 Starting SplitBills server setup..."

# Print important environment values for debugging (safe subset)
echo "Using database:"
echo "  HOST: ${DB_HOST}"
echo "  PORT: ${DB_PORT}"
echo "  NAME: ${DB_NAME}"
echo "  USER: ${DB_USER}"
echo ""

# Wait for database readiness
echo "⏳ Waiting for database at ${DB_HOST}:${DB_PORT}..."

# We'll retry until asyncpg successfully connects
until uv run python -c "import asyncpg, asyncio; asyncio.run(asyncpg.connect(
    user='${DB_USER:-$PGUSER}',
    password='${DB_PASS:-$PGPASSWORD}',
    database='${DB_NAME:-$PGDATABASE}',
    host='${DB_HOST:-$PGHOST}',
    port=${DB_PORT:-$PGPORT}
))" >/dev/null 2>&1; do
    echo "   ❌ Database not ready yet, retrying in 2s..."
    sleep 2
done



echo "✅ Database is ready."

# Run Alembic migrations
echo "🔄 Running Alembic migrations..."
uv run alembic upgrade head
echo "✅ Migrations applied successfully."

# Optionally seed data or run init scripts
if [ -f /app/app/init_db.py ]; then
    echo "⚙️ Running DB initialization script..."
    uv run python /app/app/init_db.py || echo "⚠️ No init_db.py found or it failed; continuing..."
fi

# Start the FastAPI app
echo "🚀 Launching FastAPI application..."
exec uv run uvicorn main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'
