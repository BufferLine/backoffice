#!/usr/bin/env bash
set -euo pipefail
# Soft reset: drop/recreate DB + rerun migrations. Docker stays running.
# Use this between E2E runs instead of full reset.sh.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

if [ -f .env ]; then
  set -a; source .env; set +a
fi

DB_PASSWORD="${DB_PASSWORD:-devpassword123}"

# Verify DB is reachable
if ! docker compose exec -T db pg_isready -U backoffice >/dev/null 2>&1; then
  echo "ERROR: PostgreSQL is not running. Run scripts/reset.sh first."
  exit 1
fi

# Kill server first to release DB connections
pkill -f "uvicorn app.main" 2>/dev/null || true
sleep 1

# Drop + recreate database (terminate remaining connections first)
echo "[1/3] Recreating database..."
docker compose exec -T db psql -U backoffice -d postgres \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='backoffice' AND pid <> pg_backend_pid();" \
  -c "DROP DATABASE IF EXISTS backoffice;" \
  -c "CREATE DATABASE backoffice;" > /dev/null

# Run migrations
echo "[2/3] Running migrations..."
cd backend
source .venv/bin/activate 2>/dev/null || true
DATABASE_URL="postgresql+asyncpg://backoffice:${DB_PASSWORD}@localhost:5432/backoffice" \
  alembic upgrade head 2>&1 | grep -E "^INFO|Running upgrade"

# Start server
echo "[3/3] Starting server..."
cd "$PROJECT_DIR/backend"
source .venv/bin/activate 2>/dev/null || true
DATABASE_URL="postgresql+asyncpg://backoffice:${DB_PASSWORD}@localhost:5432/backoffice" \
S3_ENDPOINT="http://localhost:9000" \
S3_ACCESS_KEY="${MINIO_ACCESS_KEY:-minioadmin}" \
S3_SECRET_KEY="${MINIO_SECRET_KEY:-miniodevpassword123}" \
S3_BUCKET="backoffice" \
JWT_SECRET="${JWT_SECRET:-dev_jwt_secret_change_in_production_32chars}" \
  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &

# Wait for server
until curl -sf http://localhost:8000/health >/dev/null 2>&1; do sleep 0.5; done
echo "Soft reset complete."
