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

API_URL="http://localhost:8000"

echo "=== Seeding Demo Data ==="

# Check server
if ! curl -sf "$API_URL/health" | grep -q '"status":"ok"'; then
  echo "ERROR: Server is not running at $API_URL"
  echo "Run: scripts/reset.sh  or  scripts/dev.sh"
  exit 1
fi

# -------------------------------------------------------------------------
# Auth: login as admin
# -------------------------------------------------------------------------
echo "[Auth] Logging in..."
LOGIN_RESP=$(curl -sf -X POST "$API_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"${TEST_EMAIL:-admin@test.local}\",\"password\":\"${TEST_PASSWORD:-TestPass123!}\"}" 2>&1) || LOGIN_RESP=""

if ! echo "$LOGIN_RESP" | grep -q "access_token"; then
  echo "ERROR: Could not log in. Run scripts/e2e.sh first to create the admin account."
  exit 1
fi

ACCESS_TOKEN=$(echo "$LOGIN_RESP" | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

api() {
  curl -sf \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "Content-Type: application/json" \
    "$@" 2>&1 || true
}

# -------------------------------------------------------------------------
# Clients
# -------------------------------------------------------------------------
echo "[Clients] Creating demo clients..."

ACME=$(api -X POST "$API_URL/api/clients" \
  -d '{"legal_name":"Acme Corp","billing_email":"ap@acme.com","default_currency":"SGD","payment_terms_days":30}')
ACME_ID=$(echo "$ACME" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "")
[ -n "$ACME_ID" ] && echo "  Created: Acme Corp ($ACME_ID)"

BETA=$(api -X POST "$API_URL/api/clients" \
  -d '{"legal_name":"Beta Labs Pte Ltd","billing_email":"finance@betalabs.io","default_currency":"USD","payment_terms_days":14}')
BETA_ID=$(echo "$BETA" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "")
[ -n "$BETA_ID" ] && echo "  Created: Beta Labs Pte Ltd ($BETA_ID)"

GAMMA=$(api -X POST "$API_URL/api/clients" \
  -d '{"legal_name":"Gamma Technologies","billing_email":"billing@gamma.tech","default_currency":"SGD","payment_terms_days":60}')
GAMMA_ID=$(echo "$GAMMA" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "")
[ -n "$GAMMA_ID" ] && echo "  Created: Gamma Technologies ($GAMMA_ID)"

# -------------------------------------------------------------------------
# Invoices
# -------------------------------------------------------------------------
echo "[Invoices] Creating demo invoices..."

if [ -n "$ACME_ID" ]; then
  # Draft invoice
  DRAFT=$(api -X POST "$API_URL/api/invoices" \
    -d "{\"client_id\":\"$ACME_ID\",\"currency\":\"SGD\",\"description\":\"Q1 consulting services\"}")
  DRAFT_ID=$(echo "$DRAFT" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "")
  if [ -n "$DRAFT_ID" ]; then
    api -X POST "$API_URL/api/invoices/$DRAFT_ID/line-items" \
      -d '{"description":"Strategy consulting","quantity":"80","unit_price":"150"}' >/dev/null
    echo "  Created draft invoice for Acme Corp"
  fi

  # Issued invoice
  ISSUED_INV=$(api -X POST "$API_URL/api/invoices" \
    -d "{\"client_id\":\"$ACME_ID\",\"currency\":\"SGD\",\"description\":\"Feb retainer\"}")
  ISSUED_INV_ID=$(echo "$ISSUED_INV" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "")
  if [ -n "$ISSUED_INV_ID" ]; then
    api -X POST "$API_URL/api/invoices/$ISSUED_INV_ID/line-items" \
      -d '{"description":"Monthly retainer","quantity":"1","unit_price":"8000"}' >/dev/null
    api -X POST "$API_URL/api/invoices/$ISSUED_INV_ID/issue" >/dev/null
    echo "  Created issued invoice for Acme Corp"
  fi
fi

if [ -n "$BETA_ID" ]; then
  BETA_INV=$(api -X POST "$API_URL/api/invoices" \
    -d "{\"client_id\":\"$BETA_ID\",\"currency\":\"USD\",\"description\":\"Development sprint\"}")
  BETA_INV_ID=$(echo "$BETA_INV" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "")
  if [ -n "$BETA_INV_ID" ]; then
    api -X POST "$API_URL/api/invoices/$BETA_INV_ID/line-items" \
      -d '{"description":"Sprint 1 - 2 weeks","quantity":"1","unit_price":"12000"}' >/dev/null
    api -X POST "$API_URL/api/invoices/$BETA_INV_ID/issue" >/dev/null
    echo "  Created issued invoice for Beta Labs"
  fi
fi

# -------------------------------------------------------------------------
# Employee + Payroll
# -------------------------------------------------------------------------
echo "[Payroll] Creating demo employee and payroll run..."

EMP=$(api -X POST "$API_URL/api/employees" \
  -d "{\"name\":\"${TEST_EMPLOYEE:-Test Employee}\",\"email\":\"user@example.com\",\"base_salary\":\"9500\",\"salary_currency\":\"SGD\",\"start_date\":\"2026-01-01\",\"work_pass_type\":\"EP\",\"tax_residency\":\"SG\"}")
EMP_ID=$(echo "$EMP" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "")
if [ -n "$EMP_ID" ]; then
  echo "  Created employee: ${TEST_EMPLOYEE:-Test Employee} ($EMP_ID)"

  # Full month payroll (Feb)
  PAY=$(api -X POST "$API_URL/api/payroll/runs" \
    -d "{\"employee_id\":\"$EMP_ID\",\"month\":\"2026-02-01\"}")
  PAY_ID=$(echo "$PAY" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "")
  if [ -n "$PAY_ID" ]; then
    api -X POST "$API_URL/api/payroll/runs/$PAY_ID/review" >/dev/null
    api -X POST "$API_URL/api/payroll/runs/$PAY_ID/finalize" >/dev/null
    echo "  Created finalized payroll run for Feb 2026"
  fi

  # Draft payroll (Mar)
  PAY2=$(api -X POST "$API_URL/api/payroll/runs" \
    -d "{\"employee_id\":\"$EMP_ID\",\"month\":\"2026-03-01\"}")
  PAY2_ID=$(echo "$PAY2" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "")
  [ -n "$PAY2_ID" ] && echo "  Created draft payroll run for Mar 2026"
fi

# -------------------------------------------------------------------------
# Expenses
# -------------------------------------------------------------------------
echo "[Expenses] Creating demo expenses..."

EXP1=$(api -X POST "$API_URL/api/expenses" \
  -d '{"expense_date":"2026-03-05","vendor":"AWS","category":"cloud","currency":"USD","amount":"342.18","description":"March AWS bill"}')
EXP1_ID=$(echo "$EXP1" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "")
if [ -n "$EXP1_ID" ]; then
  api -X POST "$API_URL/api/expenses/$EXP1_ID/confirm" >/dev/null
  echo "  Created confirmed expense: AWS cloud ($342.18 USD)"
fi

EXP2=$(api -X POST "$API_URL/api/expenses" \
  -d '{"expense_date":"2026-03-10","vendor":"Figma","category":"software","currency":"USD","amount":"45.00","description":"Figma subscription"}')
echo "  Created draft expense: Figma software"

EXP3=$(api -X POST "$API_URL/api/expenses" \
  -d '{"expense_date":"2026-03-12","vendor":"Grab","category":"travel","currency":"SGD","amount":"28.50","description":"Client meeting transport"}')
EXP3_ID=$(echo "$EXP3" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "")
if [ -n "$EXP3_ID" ]; then
  api -X POST "$API_URL/api/expenses/$EXP3_ID/confirm" >/dev/null
  echo "  Created confirmed expense: Grab travel (SGD 28.50)"
fi

# -------------------------------------------------------------------------
# Bank account + transactions
# -------------------------------------------------------------------------
echo "[Accounts] Creating demo bank account and transactions..."

ACCT=$(api -X POST "$API_URL/api/accounts" \
  -d '{"name":"DBS SGD Operating","account_type":"bank","currency":"SGD","institution":"DBS","account_number":"XXX-XXXXX-X","opening_balance":"100000","opening_balance_date":"2026-01-01"}')
ACCT_ID=$(echo "$ACCT" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "")
if [ -n "$ACCT_ID" ]; then
  echo "  Created account: DBS SGD Operating ($ACCT_ID)"

  # Inflow
  api -X POST "$API_URL/api/transactions" \
    -d "{\"account_id\":\"$ACCT_ID\",\"direction\":\"in\",\"amount\":\"8000\",\"currency\":\"SGD\",\"tx_date\":\"2026-03-15\",\"category\":\"invoice_payment\",\"status\":\"confirmed\",\"counterparty\":\"Acme Corp\",\"description\":\"Invoice payment Feb retainer\"}" >/dev/null
  echo "  Created inflow transaction: SGD 8,000"

  # Salary outflow
  api -X POST "$API_URL/api/transactions" \
    -d "{\"account_id\":\"$ACCT_ID\",\"direction\":\"out\",\"amount\":\"9500\",\"currency\":\"SGD\",\"tx_date\":\"2026-02-28\",\"category\":\"salary\",\"status\":\"confirmed\",\"counterparty\":\"${TEST_EMPLOYEE:-Test Employee}\",\"description\":\"Feb 2026 salary\"}" >/dev/null
  echo "  Created outflow transaction: SGD 9,500 (salary)"

  # AWS expense
  api -X POST "$API_URL/api/transactions" \
    -d "{\"account_id\":\"$ACCT_ID\",\"direction\":\"out\",\"amount\":\"465.00\",\"currency\":\"SGD\",\"tx_date\":\"2026-03-07\",\"category\":\"expense_payment\",\"status\":\"confirmed\",\"counterparty\":\"AWS\",\"description\":\"AWS cloud bill (USD 342.18)\"}" >/dev/null
  echo "  Created outflow transaction: SGD 465 (AWS)"
fi

echo ""
echo "=== Demo seed complete ==="
echo "  Clients:      3"
echo "  Invoices:     3-4 (draft + issued)"
echo "  Employees:    1"
echo "  Payroll runs: 2 (1 finalized, 1 draft)"
echo "  Expenses:     3"
echo "  Accounts:     1 (with 3 transactions)"
