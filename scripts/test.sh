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

cd backend
source .venv/bin/activate

# Ensure test DB exists
PGPASSWORD="${DB_PASSWORD}" psql -h localhost -U backoffice -d postgres -tc \
  "SELECT 1 FROM pg_database WHERE datname='backoffice_test'" \
  | grep -q 1 || \
  PGPASSWORD="${DB_PASSWORD}" createdb -h localhost -U backoffice backoffice_test

echo "Running tests..."
pytest tests/ -v --tb=short "$@"
