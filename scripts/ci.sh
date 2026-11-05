#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

PASS=0
FAIL=0

step() { echo -e "\n${BLUE}━━━ $1 ━━━${NC}"; }
ok()   { echo -e "${GREEN}✓ $1${NC}"; PASS=$((PASS + 1)); }
err()  { echo -e "${RED}✗ $1${NC}"; FAIL=$((FAIL + 1)); }

echo "========================================="
echo "  Backoffice CI Pipeline"
echo "========================================="

# DB password for the docker-compose Postgres (same fallback as reset.sh).
# Read only DB_PASSWORD from .env — sourcing the whole file would leak app
# settings into the pytest process.
if [ -z "${DB_PASSWORD:-}" ] && [ -f .env ]; then
  DB_PASSWORD="$(grep -E '^DB_PASSWORD=' .env | tail -1 | cut -d= -f2- || true)"
fi
DB_PASSWORD="${DB_PASSWORD:-devpassword123}"

# Make sure the compose Postgres is up; full reset if Docker isn't running.
ensure_db() {
  if ! docker compose exec -T db pg_isready -U backoffice >/dev/null 2>&1; then
    echo "Docker not running — doing full reset..."
    bash scripts/reset.sh
  fi
}

# Use soft-reset between E2E runs (fast: DB-only, no Docker restart).
# Falls back to full reset.sh if Docker isn't running yet.
soft_reset() {
  if docker compose exec -T db pg_isready -U backoffice >/dev/null 2>&1; then
    bash scripts/soft-reset.sh
  else
    echo "Docker not running — doing full reset..."
    bash scripts/reset.sh
  fi
}

# ── Setup: Python env ──
# Run every phase inside backend/.venv with backend[dev] installed, so pytest
# never picks up a global interpreter with stale dependencies. Reinstall only
# when pyproject.toml changes (reset.sh installs without the dev extras).
step "Setup: Python env (backend/.venv)"
if [ ! -d backend/.venv ]; then
  python3 -m venv backend/.venv
fi
# shellcheck disable=SC1091
source backend/.venv/bin/activate
DEPS_STAMP="backend/.venv/.ci-deps-stamp"
DEPS_HASH="$(shasum backend/pyproject.toml | cut -d' ' -f1)"
if [ "$(cat "$DEPS_STAMP" 2>/dev/null || true)" != "$DEPS_HASH" ]; then
  echo "Installing backend[dev] into backend/.venv..."
  pip install -q -e "backend[dev]"
  echo "$DEPS_HASH" > "$DEPS_STAMP"
fi
echo "Using $(python --version) at $(command -v python)"

# ── Phase 1: Unit Tests (no server needed) ──
step "Phase 1: Unit Tests"
if python -m pytest backend/tests/unit/ -q --tb=short 2>&1; then
  ok "Unit tests passed"
else
  err "Unit tests failed"
fi

# ── Phase 2: Integration Tests (pytest + Postgres, no server needed) ──
# backend/tests/test_*.py run the app in-process against a dedicated test DB;
# conftest.py drops and recreates its schema. Set TEST_DATABASE_URL to use
# your own database instead of backoffice_test in the compose Postgres.
step "Phase 2: Integration Tests"
if [ -z "${TEST_DATABASE_URL:-}" ]; then
  ensure_db
  TEST_DB_EXISTS="$(docker compose exec -T db psql -U backoffice -d postgres -tAc \
    "SELECT 1 FROM pg_database WHERE datname='backoffice_test'")"
  if [ "$TEST_DB_EXISTS" != "1" ]; then
    echo "Creating database backoffice_test..."
    docker compose exec -T db createdb -U backoffice backoffice_test
  fi
  export TEST_DATABASE_URL="postgresql+asyncpg://backoffice:${DB_PASSWORD}@localhost:5432/backoffice_test"
fi
if python -m pytest backend/tests/ --ignore=backend/tests/unit -q --tb=short 2>&1; then
  ok "Integration tests passed"
else
  err "Integration tests failed"
fi

# ── Phase 3: Soft Reset + API E2E ──
step "Phase 3: Soft Reset → API E2E"
soft_reset

if curl -sf http://localhost:8000/health | grep -q '"status":"ok"'; then
  ok "Server healthy"
else
  err "Server not ready after reset"
  echo "Skipping E2E tests."
  exit 1
fi

if bash scripts/e2e.sh 2>&1; then
  ok "API E2E passed"
else
  err "API E2E failed"
fi

# ── Phase 4: Soft Reset + CLI E2E ──
step "Phase 4: Soft Reset → CLI E2E"
soft_reset

if curl -sf http://localhost:8000/health | grep -q '"status":"ok"'; then
  ok "Server healthy"
else
  err "Server not ready after reset"
  echo "Skipping CLI E2E tests."
  exit 1
fi

if bash scripts/e2e-cli.sh 2>&1; then
  ok "CLI E2E passed"
else
  err "CLI E2E failed"
fi

# ── Summary ──
echo ""
echo "========================================="
echo -e "  CI Results: ${GREEN}${PASS} passed${NC}, ${RED}${FAIL} failed${NC}"
echo "========================================="

if [ "$FAIL" -gt 0 ]; then
  exit 1
else
  echo -e "${GREEN}All CI checks passed!${NC}"
  exit 0
fi
