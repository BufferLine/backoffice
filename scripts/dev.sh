#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Load .env
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

DB_PASSWORD="${DB_PASSWORD:-devpassword123}"
MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY:-minioadmin}"
MINIO_SECRET_KEY="${MINIO_SECRET_KEY:-miniodevpassword123}"
JWT_SECRET="${JWT_SECRET:-dev_jwt_secret_change_in_production_32chars}"

echo "=== Starting Backoffice Dev Server ==="

# Start DB + MinIO (no volume wipe)
echo "[1/4] Starting PostgreSQL + MinIO..."
docker compose up -d db minio minio-init

# Wait for DB
echo "Waiting for DB..."
until docker compose exec -T db pg_isready -U backoffice >/dev/null 2>&1; do
  sleep 1
done
echo "DB ready."

# Wait for MinIO
until curl -sf http://localhost:9000/minio/health/live >/dev/null 2>&1; do
  sleep 1
done
echo "MinIO ready."

# Check if database has tables (i.e. migrations have been run)
TABLE_COUNT=$(docker compose exec -T db psql -U backoffice -d backoffice -t -c \
  "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null | tr -d ' \n' || echo "0")

if [ "$TABLE_COUNT" = "0" ] || [ -z "$TABLE_COUNT" ]; then
  echo ""
  echo "WARNING: Database appears empty. Run scripts/reset.sh first to initialise it."
  echo ""
fi

# Set up venv if needed
echo "[2/4] Checking virtualenv..."
cd backend
if [ ! -d ".venv" ]; then
  echo "Creating virtualenv..."
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -e "." -q
else
  source .venv/bin/activate
fi

# Run pending migrations
echo "[3/4] Running any pending migrations..."
DATABASE_URL="postgresql+asyncpg://backoffice:${DB_PASSWORD}@localhost:5432/backoffice" \
  alembic upgrade head
cd "$PROJECT_DIR"

# Kill any existing uvicorn
pkill -f "uvicorn app.main" 2>/dev/null || true
sleep 1

# Start backend
echo "[4/4] Starting backend with --reload..."
cd backend
source .venv/bin/activate
DATABASE_URL="postgresql+asyncpg://backoffice:${DB_PASSWORD}@localhost:5432/backoffice" \
S3_ENDPOINT="http://localhost:9000" \
S3_ACCESS_KEY="${MINIO_ACCESS_KEY}" \
S3_SECRET_KEY="${MINIO_SECRET_KEY}" \
S3_BUCKET="backoffice" \
JWT_SECRET="${JWT_SECRET}" \
  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
cd "$PROJECT_DIR"

# Wait for server
echo "Waiting for server..."
sleep 3
until curl -sf http://localhost:8000/health >/dev/null 2>&1; do
  sleep 1
done

echo ""
echo "=== Dev Server Ready ==="
echo "API: http://localhost:8000"
echo "Docs: http://localhost:8000/docs"
echo "MinIO console: http://localhost:9001"
