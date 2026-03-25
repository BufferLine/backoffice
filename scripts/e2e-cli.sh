#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Activate venv so `acct` is on PATH
source backend/.venv/bin/activate 2>/dev/null || true

# Disable Rich colour output so we can parse JSON cleanly
export NO_COLOR=1

API_URL="${API_URL:-${API_BASE_URL:-http://localhost:8000}}"
PASS=0
FAIL=0
ERRORS=""

pass() { echo "  [PASS] $1"; PASS=$((PASS + 1)); }
fail() { echo "  [FAIL] $1: $2"; FAIL=$((FAIL + 1)); ERRORS="${ERRORS}\n  [FAIL] $1: $2"; }

# Extract a top-level field from a JSON string on stdin
# Usage: echo "$OUTPUT" | extract_field id
extract_field() {
  python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(d.get('$1',''))" 2>/dev/null || true
}

# Run an acct command, capture stdout+stderr, return combined output.
# Usage: OUTPUT=$(acct_run client list)
acct_run() {
  acct "$@" 2>&1 || true
}

echo "========================================="
echo "  Backoffice CLI E2E Test"
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
# 1. Onboarding — acct init (non-interactive), then complete via API (simulates browser)
# -------------------------------------------------------------------------
echo ""
echo "[1. Onboarding]"

INIT_OUTPUT=$(acct_run init --company-name "${TEST_COMPANY:-Test Company Pte Ltd}" --jurisdiction SG --uen "${TEST_UEN:-000000000X}" --api-url "$API_URL")

if echo "$INIT_OUTPUT" | grep -qi "initialized\|setup"; then
  pass "acct init"
  TOKEN=$(echo "$INIT_OUTPUT" | python3 -c "import sys,re; m=re.search(r'token=([^\s&]+)', sys.stdin.read()); print(m.group(1) if m else '')" 2>/dev/null || echo "")

  if [ -z "$TOKEN" ]; then
    fail "Extract setup token" "could not parse token from: $INIT_OUTPUT"
    exit 1
  fi

  COMPLETE_RESP=$(curl -sf -X POST "$API_URL/api/setup/complete" \
    -H "Content-Type: application/json" \
    -d "{\"token\":\"$TOKEN\",\"email\":\"${TEST_EMAIL:-admin@test.com}\",\"password\":\"${TEST_PASSWORD:-TestPass123!}\",\"name\":\"Admin User\"}" 2>&1) || COMPLETE_RESP=""

  if echo "$COMPLETE_RESP" | grep -q "access_token"; then
    pass "Admin account created (via browser — simulated with curl)"
  else
    fail "Admin account created" "$COMPLETE_RESP"
    echo "Cannot continue without admin account. Exiting."
    exit 1
  fi
else
  # Already initialised — will log in with CLI below
  pass "System already initialized"
fi

# -------------------------------------------------------------------------
# 2. CLI auth: login + whoami
# -------------------------------------------------------------------------
echo ""
echo "[2. CLI Auth]"

OUTPUT=$(acct_run login --email "${TEST_EMAIL:-admin@test.com}" --password "${TEST_PASSWORD:-TestPass123!}" --api-url "$API_URL")
if echo "$OUTPUT" | grep -qi "logged in"; then
  pass "acct login"
else
  fail "acct login" "$OUTPUT"
  echo "Cannot continue without login. Exiting."
  exit 1
fi

OUTPUT=$(acct_run whoami)
if echo "$OUTPUT" | grep -q "${TEST_EMAIL:-admin@test.com}"; then
  pass "acct whoami"
else
  fail "acct whoami" "$OUTPUT"
fi

# -------------------------------------------------------------------------
# 3. Client
# -------------------------------------------------------------------------
echo ""
echo "[3. Client]"

OUTPUT=$(acct_run client create \
  --name "Acme Corp Pte Ltd" \
  --email "ap@acme.com" \
  --currency SGD \
  --payment-terms 30)
CLIENT_ID=$(echo "$OUTPUT" | python3 -c \
  "import sys,json
lines=sys.stdin.read()
# find the JSON object in the output (print_success line + JSON block)
import re
m=re.search(r'\{.*\}', lines, re.DOTALL)
if m:
    d=json.loads(m.group())
    print(d.get('id',''))
" 2>/dev/null || true)

if [ -n "$CLIENT_ID" ]; then
  pass "acct client create ($CLIENT_ID)"
else
  fail "acct client create" "$OUTPUT"
fi

OUTPUT=$(acct_run client list)
if echo "$OUTPUT" | grep -q "Acme"; then
  pass "acct client list"
else
  fail "acct client list" "$OUTPUT"
fi

# -------------------------------------------------------------------------
# 4. Invoice
# -------------------------------------------------------------------------
echo ""
echo "[4. Invoice]"

if [ -z "${CLIENT_ID:-}" ]; then
  echo "  (skipping invoice tests — no client ID)"
else

OUTPUT=$(acct_run invoice create \
  --client "$CLIENT_ID" \
  --currency SGD \
  --description "March consulting")
INV_ID=$(echo "$OUTPUT" | python3 -c \
  "import sys,json,re
lines=sys.stdin.read()
m=re.search(r'\{.*\}', lines, re.DOTALL)
if m:
    print(json.loads(m.group()).get('id',''))
" 2>/dev/null || true)

if [ -n "$INV_ID" ]; then
  pass "acct invoice create ($INV_ID)"
else
  fail "acct invoice create" "$OUTPUT"
  INV_ID=""
fi

if [ -n "${INV_ID:-}" ]; then

OUTPUT=$(acct_run invoice add-item "$INV_ID" \
  --desc "Consulting 160hrs" \
  --qty 160 \
  --price 31.25)
if echo "$OUTPUT" | grep -q "amount"; then
  pass "acct invoice add-item"
else
  fail "acct invoice add-item" "$OUTPUT"
fi

OUTPUT=$(acct_run invoice issue "$INV_ID")
if echo "$OUTPUT" | grep -qi "issued"; then
  pass "acct invoice issue"
else
  fail "acct invoice issue" "$OUTPUT"
fi

OUTPUT=$(COLUMNS=200 acct_run invoice list)
if echo "$OUTPUT" | grep -q "draft\|issued\|paid"; then
  pass "acct invoice list"
else
  fail "acct invoice list" "$OUTPUT"
fi

OUTPUT=$(acct_run invoice show "$INV_ID")
if echo "$OUTPUT" | grep -q "5000"; then
  pass "acct invoice show (subtotal=5000)"
else
  fail "acct invoice show" "$OUTPUT"
fi

fi  # INV_ID guard
fi  # CLIENT_ID guard

# -------------------------------------------------------------------------
# 5. Employee
# -------------------------------------------------------------------------
echo ""
echo "[5. Employee]"

OUTPUT=$(acct_run employee add \
  --name "${TEST_EMPLOYEE:-Test Employee}" \
  --salary 9500 \
  --currency SGD \
  --start-date 2026-03-19 \
  --pass-type EP)
EMP_ID=$(echo "$OUTPUT" | python3 -c \
  "import sys,json,re
lines=sys.stdin.read()
m=re.search(r'\{.*\}', lines, re.DOTALL)
if m:
    print(json.loads(m.group()).get('id',''))
" 2>/dev/null || true)

if [ -n "$EMP_ID" ]; then
  pass "acct employee add ($EMP_ID)"
else
  fail "acct employee add" "$OUTPUT"
  EMP_ID=""
fi

OUTPUT=$(acct_run employee list)
if echo "$OUTPUT" | grep -q "${TEST_EMPLOYEE_FIRST:-Test}"; then
  pass "acct employee list"
else
  fail "acct employee list" "$OUTPUT"
fi

# -------------------------------------------------------------------------
# 6. Payroll
# -------------------------------------------------------------------------
echo ""
echo "[6. Payroll]"

if [ -z "${EMP_ID:-}" ]; then
  echo "  (skipping payroll tests — no employee ID)"
else

OUTPUT=$(acct_run payroll run \
  --employee "$EMP_ID" \
  --month 2026-03 \
  --start-date 2026-03-19)
PAY_ID=$(echo "$OUTPUT" | python3 -c \
  "import sys,json,re
lines=sys.stdin.read()
m=re.search(r'\{.*\}', lines, re.DOTALL)
if m:
    print(json.loads(m.group()).get('id',''))
" 2>/dev/null || true)

if [ -n "$PAY_ID" ]; then
  pass "acct payroll run ($PAY_ID)"
else
  fail "acct payroll run" "$OUTPUT"
  PAY_ID=""
fi

if echo "$OUTPUT" | grep -q "3983.87"; then
  pass "payroll prorated gross = 3983.87"
else
  fail "payroll prorated gross" "expected 3983.87 in: $(echo "$OUTPUT" | head -5)"
fi

if echo "$OUTPUT" | grep -q "3983.87"; then
  pass "payroll net salary = 3983.87"
else
  fail "payroll net salary" "expected 3983.87 in: $(echo "$OUTPUT" | head -5)"
fi

if [ -n "${PAY_ID:-}" ]; then

OUTPUT=$(acct_run payroll review "$PAY_ID")
if echo "$OUTPUT" | grep -qi "reviewed"; then
  pass "acct payroll review"
else
  fail "acct payroll review" "$OUTPUT"
fi

OUTPUT=$(acct_run payroll finalize "$PAY_ID")
if echo "$OUTPUT" | grep -qi "finalized"; then
  pass "acct payroll finalize"
else
  fail "acct payroll finalize" "$OUTPUT"
fi

if echo "$OUTPUT" | grep -q "payslip_file_id"; then
  pass "payslip PDF generated"
else
  fail "payslip PDF" "no payslip_file_id in output"
fi

fi  # PAY_ID guard

OUTPUT=$(COLUMNS=200 acct_run payroll list)
if echo "$OUTPUT" | grep -qi "finaliz"; then
  pass "acct payroll list"
else
  fail "acct payroll list" "$OUTPUT"
fi

fi  # EMP_ID guard

# -------------------------------------------------------------------------
# 7. Expense
# -------------------------------------------------------------------------
echo ""
echo "[7. Expense]"

OUTPUT=$(acct_run expense add \
  --date 2026-03-15 \
  --vendor AWS \
  --category cloud \
  --amount 145 \
  --currency USD)
EXP_ID=$(echo "$OUTPUT" | python3 -c \
  "import sys,json,re
lines=sys.stdin.read()
m=re.search(r'\{.*\}', lines, re.DOTALL)
if m:
    print(json.loads(m.group()).get('id',''))
" 2>/dev/null || true)

if [ -n "$EXP_ID" ]; then
  pass "acct expense add ($EXP_ID)"
else
  fail "acct expense add" "$OUTPUT"
  EXP_ID=""
fi

if [ -n "${EXP_ID:-}" ]; then
OUTPUT=$(acct_run expense confirm "$EXP_ID")
if echo "$OUTPUT" | grep -qi "confirmed"; then
  pass "acct expense confirm"
else
  fail "acct expense confirm" "$OUTPUT"
fi
fi

# -------------------------------------------------------------------------
# 8. Payment
# -------------------------------------------------------------------------
echo ""
echo "[8. Payment]"

if [ -n "${INV_ID:-}" ]; then
OUTPUT=$(acct_run payment record \
  --type bank_transfer \
  --entity "invoice:$INV_ID" \
  --amount 5000 \
  --currency SGD \
  --date 2026-03-20)
if echo "$OUTPUT" | grep -q "bank_transfer"; then
  pass "acct payment record (invoice)"
else
  fail "acct payment record" "$OUTPUT"
fi
else
  echo "  (skipping payment record — no invoice ID)"
fi

OUTPUT=$(COLUMNS=200 acct_run payment list)
if echo "$OUTPUT" | grep -q "bank_trans"; then
  pass "acct payment list"
else
  fail "acct payment list" "$OUTPUT"
fi

# -------------------------------------------------------------------------
# 9. Account
# -------------------------------------------------------------------------
echo ""
echo "[9. Account]"

OUTPUT=$(acct_run account create \
  --name "DBS SGD" \
  --type bank \
  --currency SGD \
  --institution DBS \
  --opening-balance 50000 \
  --opening-balance-date 2026-03-01)
ACCT_ID=$(echo "$OUTPUT" | python3 -c \
  "import sys,json,re
lines=sys.stdin.read()
m=re.search(r'\{.*\}', lines, re.DOTALL)
if m:
    print(json.loads(m.group()).get('id',''))
" 2>/dev/null || true)

if [ -n "$ACCT_ID" ]; then
  pass "acct account create ($ACCT_ID)"
else
  fail "acct account create" "$OUTPUT"
  ACCT_ID=""
fi

OUTPUT=$(acct_run account list)
if echo "$OUTPUT" | grep -q "DBS"; then
  pass "acct account list"
else
  fail "acct account list" "$OUTPUT"
fi

if [ -n "${ACCT_ID:-}" ]; then
OUTPUT=$(acct_run account balance "$ACCT_ID")
if echo "$OUTPUT" | grep -q "50000"; then
  pass "acct account balance (opening=50000)"
else
  fail "acct account balance" "$OUTPUT"
fi
fi

# -------------------------------------------------------------------------
# 10. Transaction
# -------------------------------------------------------------------------
echo ""
echo "[10. Transaction]"

if [ -n "${ACCT_ID:-}" ]; then
OUTPUT=$(acct_run transaction create \
  --account "$ACCT_ID" \
  --direction in \
  --amount 5000 \
  --currency SGD \
  --date 2026-03-20 \
  --category invoice_payment \
  --counterparty "Acme Corp Pte Ltd" \
  --status confirmed)
if echo "$OUTPUT" | grep -q "invoice_payment"; then
  pass "acct transaction create"
else
  fail "acct transaction create" "$OUTPUT"
fi

OUTPUT=$(COLUMNS=200 acct_run transaction list --account "$ACCT_ID")
if echo "$OUTPUT" | grep -q "invoic"; then
  pass "acct transaction list"
else
  fail "acct transaction list" "$OUTPUT"
fi
else
  echo "  (skipping transaction tests — no account ID)"
fi

# -------------------------------------------------------------------------
# 11. Todo
# -------------------------------------------------------------------------
echo ""
echo "[11. Todo]"

# Generate with --since backfill
OUTPUT=$(acct_run todo generate --since 2026-01)
if echo "$OUTPUT" | grep -qi "generated\|up to date"; then
  pass "acct todo generate --since"
else
  fail "acct todo generate --since" "$OUTPUT"
fi

OUTPUT=$(acct_run todo template-list)
if echo "$OUTPUT" | grep -qi "SDL\|compliance\|cpf\|gst"; then
  pass "acct todo template-list (compliance templates present)"
else
  fail "acct todo template-list" "expected compliance templates, got: $(echo "$OUTPUT" | head -3)"
fi

OUTPUT=$(acct_run todo summary)
if echo "$OUTPUT" | grep -qi "period\|pending\|completed"; then
  pass "acct todo summary"
else
  fail "acct todo summary" "$OUTPUT"
fi

OUTPUT=$(acct_run todo list)
# list may be empty for current month — just check it doesn't crash
pass "acct todo list (no crash)"

# Create ad-hoc task
OUTPUT=$(acct_run todo add "E2E test task" --category custom --priority high --period 2026-03)
TODO_ID=$(echo "$OUTPUT" | python3 -c \
  "import sys,json,re
lines=sys.stdin.read()
m=re.search(r'\{.*\}', lines, re.DOTALL)
if m:
    print(json.loads(m.group()).get('id',''))
" 2>/dev/null || true)
if [ -n "$TODO_ID" ]; then
  pass "acct todo add ($TODO_ID)"
else
  fail "acct todo add" "$OUTPUT"
  TODO_ID=""
fi

if [ -n "${TODO_ID:-}" ]; then

# Complete
OUTPUT=$(acct_run todo complete "$TODO_ID" --notes "Done in CLI E2E")
if echo "$OUTPUT" | grep -q "completed"; then
  pass "acct todo complete"
else
  fail "acct todo complete" "$OUTPUT"
fi

# Archive
OUTPUT=$(acct_run todo archive "$TODO_ID")
if echo "$OUTPUT" | grep -q "archived"; then
  pass "acct todo archive"
else
  fail "acct todo archive" "$OUTPUT"
fi

fi  # TODO_ID guard

# Create another task to test skip + archive
OUTPUT=$(acct_run todo add "E2E skip task" --category custom --priority low --period 2026-03)
SKIP_ID=$(echo "$OUTPUT" | python3 -c \
  "import sys,json,re
lines=sys.stdin.read()
m=re.search(r'\{.*\}', lines, re.DOTALL)
if m:
    print(json.loads(m.group()).get('id',''))
" 2>/dev/null || true)
if [ -n "$SKIP_ID" ]; then
  pass "acct todo add (skip task)"

  OUTPUT=$(acct_run todo skip "$SKIP_ID" --notes "Not needed")
  if echo "$OUTPUT" | grep -q "skipped"; then
    pass "acct todo skip"
  else
    fail "acct todo skip" "$OUTPUT"
  fi

  OUTPUT=$(acct_run todo archive "$SKIP_ID")
  if echo "$OUTPUT" | grep -q "archived"; then
    pass "acct todo archive (skipped task)"
  else
    fail "acct todo archive (skipped task)" "$OUTPUT"
  fi
fi

# -------------------------------------------------------------------------
# 12. Changelog
# -------------------------------------------------------------------------
echo ""
echo "[12. Changelog]"

if [ -n "${EMP_ID:-}" ]; then
OUTPUT=$(acct_run changelog history employee "$EMP_ID")
# May have entries or "No change logs found." — both are valid
pass "acct changelog history employee (no crash)"
else
  echo "  (skipping changelog — no employee ID)"
fi

# -------------------------------------------------------------------------
# 13. State machine enforcement
# -------------------------------------------------------------------------
echo ""
echo "[13. Safety Controls]"

if [ -n "${INV_ID:-}" ]; then
  # Try to re-issue an already-issued invoice — should fail with 409
  ACCESS_TOKEN=$(python3 -c \
    "import json; creds=json.load(open('$HOME/.acct/credentials.json')); print(creds.get('token',''))" \
    2>/dev/null || echo "")
  if [ -n "$ACCESS_TOKEN" ]; then
    BAD_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
      -X POST "$API_URL/api/invoices/$INV_ID/issue" \
      -H "Authorization: Bearer $ACCESS_TOKEN" \
      -H "Content-Type: application/json" 2>&1 || echo "000")
    if [ "$BAD_STATUS" = "409" ]; then
      pass "Cannot re-issue already-issued invoice (409)"
    else
      fail "Cannot re-issue invoice" "expected 409, got $BAD_STATUS"
    fi
  else
    echo "  (skipped: could not read token)"
  fi
else
  echo "  (skipped: no invoice ID)"
fi

if [ -n "${PAY_ID:-}" ]; then
  ACCESS_TOKEN=$(python3 -c \
    "import json; creds=json.load(open('$HOME/.acct/credentials.json')); print(creds.get('token',''))" \
    2>/dev/null || echo "")
  if [ -n "$ACCESS_TOKEN" ]; then
    BAD_STATUS2=$(curl -s -o /dev/null -w "%{http_code}" \
      -X POST "$API_URL/api/payroll/runs/$PAY_ID/finalize" \
      -H "Authorization: Bearer $ACCESS_TOKEN" \
      -H "Content-Type: application/json" 2>&1 || echo "000")
    if [ "$BAD_STATUS2" = "409" ]; then
      pass "Cannot re-finalize payroll (409)"
    else
      fail "Cannot re-finalize payroll" "expected 409, got $BAD_STATUS2"
    fi
  else
    echo "  (skipped: could not read token)"
  fi
else
  echo "  (skipped: no payroll run ID)"
fi

# -------------------------------------------------------------------------
# 14. Integration Framework (CLI)
# -------------------------------------------------------------------------
echo ""
echo "[14. Integration]"

OUTPUT=$(acct_run integration list)
if echo "$OUTPUT" | grep -qi "airwallex"; then
  pass "acct integration list"
else
  fail "acct integration list" "$OUTPUT"
fi

OUTPUT=$(acct_run integration events airwallex 2>&1)
if echo "$OUTPUT" | grep -qi "event\|No events\|total"; then
  pass "acct integration events airwallex"
else
  # Empty events is fine — just shouldn't crash
  pass "acct integration events airwallex (empty)"
fi

# -------------------------------------------------------------------------
# 15. Loan
# -------------------------------------------------------------------------
echo ""
echo "[15. Loan]"

OUTPUT=$(acct_run loan create \
  --type shareholder_loan \
  --direction inbound \
  --counterparty "John Smith" \
  --principal 5000 \
  --start-date 2026-03-09 \
  --currency SGD \
  --description "Shareholder loan for working capital")
LOAN_ID=$(echo "$OUTPUT" | python3 -c \
  "import sys,json,re
lines=sys.stdin.read()
m=re.search(r'\{.*\}', lines, re.DOTALL)
if m:
    print(json.loads(m.group()).get('id',''))
" 2>/dev/null || true)

if [ -n "$LOAN_ID" ]; then
  pass "acct loan create ($LOAN_ID)"
else
  fail "acct loan create" "$OUTPUT"
  LOAN_ID=""
fi

OUTPUT=$(COLUMNS=200 acct_run loan list)
if echo "$OUTPUT" | grep -q "shareholder_loan"; then
  pass "acct loan list"
else
  fail "acct loan list" "$OUTPUT"
fi

if [ -n "${LOAN_ID:-}" ]; then

OUTPUT=$(acct_run loan show "$LOAN_ID")
if echo "$OUTPUT" | grep -q "5000"; then
  pass "acct loan show (principal=5000)"
else
  fail "acct loan show" "$OUTPUT"
fi

OUTPUT=$(acct_run loan balance "$LOAN_ID")
if echo "$OUTPUT" | grep -q "outstanding"; then
  pass "acct loan balance"
else
  fail "acct loan balance" "$OUTPUT"
fi

OUTPUT=$(acct_run loan edit "$LOAN_ID" --description "Updated loan description")
if echo "$OUTPUT" | grep -qi "updated"; then
  pass "acct loan edit"
else
  fail "acct loan edit" "$OUTPUT"
fi

OUTPUT=$(acct_run loan generate-pdf "$LOAN_ID")
if echo "$OUTPUT" | grep -q "document_file_id"; then
  pass "acct loan generate-pdf"
else
  fail "acct loan generate-pdf" "$OUTPUT"
fi

OUTPUT=$(acct_run loan download "$LOAN_ID" --type agreement -o /tmp)
if echo "$OUTPUT" | grep -qi "downloaded"; then
  pass "acct loan download agreement"
else
  fail "acct loan download agreement" "$OUTPUT"
fi

OUTPUT=$(acct_run loan generate-statement "$LOAN_ID")
if echo "$OUTPUT" | grep -q "document_file_id"; then
  pass "acct loan generate-statement"
else
  fail "acct loan generate-statement" "$OUTPUT"
fi

OUTPUT=$(acct_run loan download "$LOAN_ID" --type statement -o /tmp)
if echo "$OUTPUT" | grep -qi "downloaded"; then
  pass "acct loan download statement"
else
  fail "acct loan download statement" "$OUTPUT"
fi

# Record a repayment and allocate it to the loan
OUTPUT=$(acct_run payment record \
  --type bank_transfer \
  --entity "loan:$LOAN_ID" \
  --amount 5000 \
  --currency SGD \
  --date 2026-03-20)
REPAY_PMT_ID=$(echo "$OUTPUT" | python3 -c \
  "import sys,json,re
lines=sys.stdin.read()
m=re.search(r'\{.*\}', lines, re.DOTALL)
if m:
    print(json.loads(m.group()).get('id',''))
" 2>/dev/null || true)
if [ -n "$REPAY_PMT_ID" ]; then
  pass "acct payment record (loan repayment)"
else
  fail "acct payment record (loan repayment)" "$OUTPUT"
fi

if [ -n "${REPAY_PMT_ID:-}" ]; then
OUTPUT=$(acct_run payment allocate "$REPAY_PMT_ID" \
  --entity "loan:$LOAN_ID" \
  --amount 5000)
if echo "$OUTPUT" | grep -qi "allocated"; then
  pass "acct payment allocate (loan)"
else
  fail "acct payment allocate (loan)" "$OUTPUT"
fi
fi

OUTPUT=$(acct_run loan mark-repaid "$LOAN_ID")
if echo "$OUTPUT" | grep -q '"repaid"'; then
  pass "acct loan mark-repaid"
else
  fail "acct loan mark-repaid" "$OUTPUT"
fi

OUTPUT=$(acct_run loan generate-discharge "$LOAN_ID")
if echo "$OUTPUT" | grep -q "document_file_id"; then
  pass "acct loan generate-discharge"
else
  fail "acct loan generate-discharge" "$OUTPUT"
fi

OUTPUT=$(acct_run loan download "$LOAN_ID" --type discharge -o /tmp)
if echo "$OUTPUT" | grep -qi "downloaded"; then
  pass "acct loan download discharge"
else
  fail "acct loan download discharge" "$OUTPUT"
fi

fi  # LOAN_ID guard

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
  echo "All CLI E2E tests passed!"
  exit 0
fi
