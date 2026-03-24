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

# ── Phase 1: Unit Tests (no server needed) ──
step "Phase 1: Unit Tests"
if python -m pytest backend/tests/unit/ -q --tb=short 2>&1; then
  ok "Unit tests passed"
else
  err "Unit tests failed"
fi

# ── Phase 2: Soft Reset + API E2E ──
step "Phase 2: Soft Reset → API E2E"
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

# ── Phase 3: Soft Reset + CLI E2E ──
step "Phase 3: Soft Reset → CLI E2E"
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
