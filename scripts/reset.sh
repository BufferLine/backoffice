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

echo "=== Resetting Backoffice System ==="

# Stop all services
echo "[1/5] Stopping services..."
docker compose down -v 2>/dev/null || true
pkill -f "uvicorn app.main" 2>/dev/null || true
sleep 1

# Start DB + MinIO fresh
echo "[2/5] Starting PostgreSQL + MinIO..."
docker compose up -d db minio minio-init
echo "Waiting for services to be healthy..."
sleep 3

# Wait for DB to be ready
echo "Waiting for DB..."
until docker compose exec -T db pg_isready -U backoffice >/dev/null 2>&1; do
  sleep 1
done
echo "DB ready."

# Wait for MinIO
echo "Waiting for MinIO..."
until curl -sf http://localhost:9000/minio/health/live >/dev/null 2>&1; do
  sleep 1
done
echo "MinIO ready."

# Create/recreate database
echo "[3/5] Recreating database..."
docker compose exec -T db psql -U backoffice -d postgres \
  -c "DROP DATABASE IF EXISTS backoffice;" \
  -c "CREATE DATABASE backoffice;"

# Run migrations
echo "[4/5] Running Alembic migrations..."
cd backend
if [ ! -d ".venv" ]; then
  echo "Creating virtualenv..."
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -e "." -q
else
  source .venv/bin/activate
fi

DATABASE_URL="postgresql+asyncpg://backoffice:${DB_PASSWORD}@localhost:5432/backoffice" \
  alembic upgrade head
cd "$PROJECT_DIR"

# Kill any existing uvicorn
pkill -f "uvicorn app.main" 2>/dev/null || true
sleep 1

# Start backend with reload
echo "[5/5] Starting backend..."
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
echo "=== Reset Complete ==="
echo "Server running at http://localhost:8000"
echo "MinIO console at http://localhost:9001"
echo ""
echo "Next: run 'scripts/e2e.sh' to run end-to-end tests"
echo "  or: call POST /api/setup/init to set up your company"
