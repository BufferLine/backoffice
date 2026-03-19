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
PASS=0
FAIL=0
ERRORS=""

pass() { echo "  [PASS] $1"; PASS=$((PASS + 1)); }
fail() { echo "  [FAIL] $1: $2"; FAIL=$((FAIL + 1)); ERRORS="${ERRORS}\n  [FAIL] $1: $2"; }

check() {
  # Usage: check "description" "command" "expected_substring"
  local desc="$1"
  local cmd="$2"
  local expected="$3"
  local output
  output=$(eval "$cmd" 2>&1) || true
  if echo "$output" | grep -q "$expected"; then
    pass "$desc"
  else
    fail "$desc" "expected '$expected', got: $(echo "$output" | head -3)"
  fi
}

echo "========================================="
echo "  Backoffice E2E Test"
echo "========================================="
echo ""

# -------------------------------------------------------------------------
# Pre-check: server health
# -------------------------------------------------------------------------
echo "[Pre-check]"
if ! curl -sf "$API_URL/health" | grep -q '"status":"ok"'; then
  echo "  ERROR: Server is not running at $API_URL"
  echo "  Run: scripts/reset.sh  or  scripts/dev.sh"
  exit 1
fi
pass "Server health"

# -------------------------------------------------------------------------
# Step 1: Onboarding / login
# -------------------------------------------------------------------------
echo ""
echo "[1. Onboarding / Auth]"

ACCESS_TOKEN=""

# Try init first
INIT_RESP=$(curl -sf -X POST "$API_URL/api/setup/init" \
  -H "Content-Type: application/json" \
  -d '{"company_name":"Bufferline Pte Ltd","jurisdiction":"SG","uen":"202412345A"}' 2>&1) || INIT_RESP=""

if echo "$INIT_RESP" | grep -q "setup_url"; then
  pass "System init"
  TOKEN=$(echo "$INIT_RESP" | python3 -c "import sys,json;print(json.load(sys.stdin)['setup_url'].split('token=')[1])" 2>/dev/null || echo "")

  if [ -z "$TOKEN" ]; then
    fail "Extract setup token" "could not parse token from: $INIT_RESP"
    exit 1
  fi

  COMPLETE_RESP=$(curl -sf -X POST "$API_URL/api/setup/complete" \
    -H "Content-Type: application/json" \
    -d "{\"token\":\"$TOKEN\",\"email\":\"admin@bufferline.com\",\"password\":\"Admin123!\",\"name\":\"Admin User\"}" 2>&1) || COMPLETE_RESP=""

  if echo "$COMPLETE_RESP" | grep -q "access_token"; then
    pass "Admin account created"
    ACCESS_TOKEN=$(echo "$COMPLETE_RESP" | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])" 2>/dev/null || echo "")
  else
    fail "Admin account created" "$COMPLETE_RESP"
    echo "Cannot continue without auth. Exiting."
    exit 1
  fi
else
  # System already initialized — try login
  LOGIN_RESP=$(curl -sf -X POST "$API_URL/api/auth/login" \
    -H "Content-Type: application/json" \
    -d '{"email":"admin@bufferline.com","password":"Admin123!"}' 2>&1) || LOGIN_RESP=""

  if echo "$LOGIN_RESP" | grep -q "access_token"; then
    pass "System already initialized, logged in"
    ACCESS_TOKEN=$(echo "$LOGIN_RESP" | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])" 2>/dev/null || echo "")
  else
    fail "Login" "$LOGIN_RESP"
    exit 1
  fi
fi

if [ -z "$ACCESS_TOKEN" ]; then
  fail "Access token" "empty token"
  exit 1
fi

# Helper: authenticated API call
# api <extra_curl_args...>  — the URL must be among the args
api() {
  curl -sf \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "Content-Type: application/json" \
    "$@" 2>&1 || true
}

# -------------------------------------------------------------------------
# Step 2: Verify auth
# -------------------------------------------------------------------------
echo ""
echo "[2. Authentication]"
ME=$(api "$API_URL/api/auth/me")
check "Get current user"   "echo '$ME'" "admin@bufferline.com"
check "Has superadmin role" "echo '$ME'" "superadmin"

# -------------------------------------------------------------------------
# Step 3: Client
# -------------------------------------------------------------------------
echo ""
echo "[3. Client Management]"
CLIENT=$(api -X POST "$API_URL/api/clients" \
  -d '{"legal_name":"Acme Corp","billing_email":"ap@acme.com","default_currency":"SGD","payment_terms_days":30}')
CLIENT_ID=$(echo "$CLIENT" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "")
if [ -n "$CLIENT_ID" ]; then
  pass "Create client ($CLIENT_ID)"
else
  fail "Create client" "$CLIENT"
  CLIENT_ID=""
fi

if [ -z "$CLIENT_ID" ]; then
  echo "  Cannot continue invoice tests without a client. Skipping steps 4-7."
else

# -------------------------------------------------------------------------
# Step 4: Invoice lifecycle
# -------------------------------------------------------------------------
echo ""
echo "[4. Invoice Lifecycle]"
INV=$(api -X POST "$API_URL/api/invoices" \
  -d "{\"client_id\":\"$CLIENT_ID\",\"currency\":\"SGD\",\"description\":\"March consulting\"}")
INV_ID=$(echo "$INV" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "")
check "Create invoice (draft)" "echo '$INV'" '"status":"draft"'

if [ -n "$INV_ID" ]; then
  # Add line item
  ITEM=$(api -X POST "$API_URL/api/invoices/$INV_ID/line-items" \
    -d '{"description":"Consulting 160hrs","quantity":"160","unit_price":"31.25"}')
  check "Add line item" "echo '$ITEM'" '"amount"'

  # Issue
  ISSUED=$(api -X POST "$API_URL/api/invoices/$INV_ID/issue")
  check "Issue invoice"        "echo '$ISSUED'" '"status":"issued"'
  check "Has invoice number"   "echo '$ISSUED'" "INV-"
  check "Subtotal = 5000"      "echo '$ISSUED'" '"subtotal_amount":"5000'

  # -------------------------------------------------------------------------
  # Step 7: Payment + Link (must come before checking invoice paid status)
  # -------------------------------------------------------------------------
  echo ""
  echo "[7. Payment]"
  PMNT=$(api -X POST "$API_URL/api/payments" \
    -d '{"payment_type":"bank_transfer","payment_date":"2026-03-20","currency":"SGD","amount":"5000.00","bank_reference":"TRF-001"}')
  PMNT_ID=$(echo "$PMNT" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "")
  check "Record payment" "echo '$PMNT'" '"payment_type":"bank_transfer"'

  if [ -n "$PMNT_ID" ]; then
    # link_payment automatically transitions invoice to "paid"
    LINK=$(api -X POST "$API_URL/api/payments/$PMNT_ID/link" \
      -d "{\"related_entity_type\":\"invoice\",\"related_entity_id\":\"$INV_ID\"}")
    check "Link payment to invoice" "echo '$LINK'" '"related_entity_id"'

    # Verify invoice is now paid (link_payment handles the transition)
    INV_FINAL=$(api "$API_URL/api/invoices/$INV_ID")
    check "Invoice status = paid" "echo '$INV_FINAL'" '"status":"paid"'
  else
    fail "Record payment" "$PMNT"
  fi
else
  fail "Invoice ID" "could not parse invoice id"
fi

fi  # end CLIENT_ID guard

# -------------------------------------------------------------------------
# Step 5: Employee + Payroll
# -------------------------------------------------------------------------
echo ""
echo "[5. Payroll Lifecycle]"
EMP=$(api -X POST "$API_URL/api/employees" \
  -d '{"name":"Sangwon Seo","base_salary":"9500","salary_currency":"SGD","start_date":"2026-03-19","work_pass_type":"EP","tax_residency":"SG"}')
EMP_ID=$(echo "$EMP" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "")
check "Create employee" "echo '$EMP'" "Sangwon"

if [ -n "$EMP_ID" ]; then
  PAY=$(api -X POST "$API_URL/api/payroll/runs" \
    -d "{\"employee_id\":\"$EMP_ID\",\"month\":\"2026-03-01\",\"start_date\":\"2026-03-19\"}")
  PAY_ID=$(echo "$PAY" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "")
  check "Create payroll run" "echo '$PAY'" '"status":"draft"'
  check "Days worked = 13"   "echo '$PAY'" '"days_worked":13'
  check "Prorated gross"     "echo '$PAY'" '"prorated_gross_salary":"3983.87'
  check "SDL deduction"      "echo '$PAY'" '"deduction_type":"sdl"'
  check "Net salary"         "echo '$PAY'" '"net_salary":"3973.91'

  if [ -n "$PAY_ID" ]; then
    REV=$(api -X POST "$API_URL/api/payroll/runs/$PAY_ID/review")
    check "Review payroll" "echo '$REV'" '"status":"reviewed"'

    FIN=$(api -X POST "$API_URL/api/payroll/runs/$PAY_ID/finalize")
    check "Finalize payroll" "echo '$FIN'" '"status":"finalized"'
    check "Has payslip PDF"  "echo '$FIN'" '"payslip_file_id"'
  else
    fail "Payroll run ID" "could not parse payroll run id"
  fi
else
  fail "Employee ID" "could not parse employee id"
fi

# -------------------------------------------------------------------------
# Step 6: Expense
# -------------------------------------------------------------------------
echo ""
echo "[6. Expense]"
EXP=$(api -X POST "$API_URL/api/expenses" \
  -d '{"expense_date":"2026-03-15","vendor":"AWS","category":"cloud","currency":"USD","amount":"145.00"}')
EXP_ID=$(echo "$EXP" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "")
check "Create expense" "echo '$EXP'" '"status":"draft"'

if [ -n "$EXP_ID" ]; then
  CONF=$(api -X POST "$API_URL/api/expenses/$EXP_ID/confirm")
  check "Confirm expense" "echo '$CONF'" '"status":"confirmed"'
else
  fail "Expense ID" "could not parse expense id"
fi

# -------------------------------------------------------------------------
# Step 8: Account + Transaction
# -------------------------------------------------------------------------
echo ""
echo "[8. Account Balance]"
ACCT=$(api -X POST "$API_URL/api/accounts" \
  -d '{"name":"DBS SGD","account_type":"bank","currency":"SGD","institution":"DBS","opening_balance":"50000","opening_balance_date":"2026-03-01"}')
ACCT_ID=$(echo "$ACCT" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "")
check "Create account" "echo '$ACCT'" '"account_type":"bank"'

if [ -n "$ACCT_ID" ]; then
  TXN=$(api -X POST "$API_URL/api/transactions" \
    -d "{\"account_id\":\"$ACCT_ID\",\"direction\":\"in\",\"amount\":\"5000\",\"currency\":\"SGD\",\"tx_date\":\"2026-03-20\",\"category\":\"invoice_payment\",\"status\":\"confirmed\",\"description\":\"Acme Corp payment\"}")
  check "Create transaction" "echo '$TXN'" '"direction":"in"'

  BAL=$(api "$API_URL/api/accounts/$ACCT_ID/balance")
  check "Account balance" "echo '$BAL'" '"current_balance"'
else
  fail "Account ID" "could not parse account id"
fi

# -------------------------------------------------------------------------
# Step 9: Task templates
# -------------------------------------------------------------------------
echo ""
echo "[9. Task/Todo]"
TASKS=$(api "$API_URL/api/tasks/templates")
TASK_COUNT=$(echo "$TASKS" | python3 -c "import sys,json;d=json.load(sys.stdin);print(len(d) if isinstance(d,list) else 0)" 2>/dev/null || echo "0")
if [ "$TASK_COUNT" -ge 10 ] 2>/dev/null; then
  pass "Compliance templates seeded ($TASK_COUNT templates)"
else
  fail "Compliance templates seeded" "expected >=10, got: $TASK_COUNT. Response: $(echo "$TASKS" | head -c 200)"
fi

# -------------------------------------------------------------------------
# Step 10: State machine enforcement
# -------------------------------------------------------------------------
echo ""
echo "[10. Safety Controls]"

if [ -n "${INV_ID:-}" ]; then
  # Try to issue already-paid invoice — should fail with 409
  BAD_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_URL/api/invoices/$INV_ID/issue" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "Content-Type: application/json" 2>&1 || echo "000")
  if [ "$BAD_STATUS" = "409" ]; then
    pass "Cannot re-issue paid invoice (409)"
  else
    fail "Cannot re-issue paid invoice" "expected 409, got $BAD_STATUS"
  fi
else
  echo "  (skipped: no invoice id)"
fi

if [ -n "${PAY_ID:-}" ]; then
  # Try to finalize already-finalized payroll — should fail with 409
  BAD_STATUS2=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_URL/api/payroll/runs/$PAY_ID/finalize" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "Content-Type: application/json" 2>&1 || echo "000")
  if [ "$BAD_STATUS2" = "409" ]; then
    pass "Cannot re-finalize payroll (409)"
  else
    fail "Cannot re-finalize payroll" "expected 409, got $BAD_STATUS2"
  fi
else
  echo "  (skipped: no payroll run id)"
fi

# -------------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------------
echo ""
echo "========================================="
echo "  Results: $PASS passed, $FAIL failed"
echo "========================================="

if [ "$FAIL" -gt 0 ]; then
  printf "\nFailures:%b\n" "$ERRORS"
  exit 1
else
  echo "All E2E tests passed!"
  exit 0
fi
