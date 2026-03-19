# Backoffice Ops System — MVP Implementation Plan

## 1. Requirements Summary

싱가포르 기반 단일 법인의 backoffice operations 자동화 시스템.
셀프호스트, 멀티유저(RBAC), CLI + API + Frontend 통합.

### 핵심 결정 사항

| 항목 | 결정 |
|------|------|
| MVP 범위 | intro.md 전체 (Invoice, Payroll, Expense, Payment, Export, Automation, Agent Skills) |
| 인프라 | Docker Compose (PostgreSQL + MinIO + Backend + Frontend) |
| Auth | invite-only + JWT (Frontend: access+refresh, CLI: long-lived API token) |
| RBAC | 도메인별 permission 기반 (`invoice:read`, `payroll:write` 등) |
| Multi-currency | SGD/USD/KRW/USDC/USDT + currencies 테이블로 동적 추가 |
| FX | 수동 입력 기본, API 연동은 로드맵 |
| Payroll | EP holder → SDL만 적용, deduction은 범용 구조 (플러그인식) |
| PDF | Jinja2 + WeasyPrint, 파일 기반 템플릿 |
| Export | Generic CSV 기본 + pluggable formatter |
| Notification | 미포함 (agent 대체) |
| 법인 | 단일 법인 (entity_id 없음) |
| Jurisdiction | 싱가포르 기본, 모듈화로 multi-national 대비 |

---

## 2. Tech Stack

```
Backend:    Python 3.12 + FastAPI + SQLAlchemy 2.0 + Alembic
CLI:        Python + Typer
DB:         PostgreSQL 16
Storage:    MinIO (S3-compatible), local fs fallback for dev
Frontend:   Next.js 15 + TypeScript + Tailwind CSS
PDF:        Jinja2 + WeasyPrint
Scheduler:  APScheduler (in-process) or cron (Docker)
Container:  Docker Compose
Testing:    pytest + httpx (API), Playwright (E2E)
```

---

## 3. Project Structure

```
backoffice/
├── backend/
│   ├── alembic/                    # DB migrations
│   │   └── versions/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                 # FastAPI app entry
│   │   ├── config.py               # Settings (pydantic-settings)
│   │   ├── database.py             # SQLAlchemy engine + session
│   │   ├── models/                 # SQLAlchemy models
│   │   │   ├── __init__.py
│   │   │   ├── user.py
│   │   │   ├── client.py
│   │   │   ├── invoice.py
│   │   │   ├── payroll.py
│   │   │   ├── expense.py
│   │   │   ├── payment.py
│   │   │   ├── file.py
│   │   │   ├── export.py
│   │   │   ├── audit.py
│   │   │   ├── currency.py
│   │   │   ├── company.py
│   │   │   └── bank_transaction.py
│   │   ├── schemas/                # Pydantic request/response schemas
│   │   │   ├── __init__.py
│   │   │   ├── user.py
│   │   │   ├── invoice.py
│   │   │   ├── payroll.py
│   │   │   ├── expense.py
│   │   │   ├── payment.py
│   │   │   └── export.py
│   │   ├── services/               # Business logic
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── invoice.py
│   │   │   ├── payroll.py
│   │   │   ├── expense.py
│   │   │   ├── payment.py
│   │   │   ├── export.py
│   │   │   ├── pdf.py
│   │   │   ├── file_storage.py
│   │   │   └── bank_reconciliation.py
│   │   ├── api/                    # FastAPI routers
│   │   │   ├── __init__.py
│   │   │   ├── deps.py             # Dependency injection (auth, db session)
│   │   │   ├── auth.py
│   │   │   ├── users.py
│   │   │   ├── invoices.py
│   │   │   ├── payroll.py
│   │   │   ├── expenses.py
│   │   │   ├── payments.py
│   │   │   ├── exports.py
│   │   │   └── bank_reconciliation.py
│   │   ├── statement_parsers/      # Bank statement parsers (pluggable)
│   │   │   ├── __init__.py
│   │   │   ├── base.py             # AbstractStatementParser
│   │   │   ├── airwallex.py
│   │   │   ├── dbs.py
│   │   │   └── generic.py          # 범용 CSV (컬럼 매핑 지정)
│   │   ├── state_machines/         # State transition definitions
│   │   │   ├── __init__.py
│   │   │   ├── invoice.py
│   │   │   └── payroll.py
│   │   ├── jurisdiction/           # Jurisdiction-specific logic (모듈화)
│   │   │   ├── __init__.py
│   │   │   ├── base.py             # Abstract base
│   │   │   └── singapore.py        # SG: SDL, GST rules
│   │   ├── export_formatters/      # Pluggable export formatters
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   └── generic_csv.py
│   │   └── templates/              # PDF templates (Jinja2 HTML)
│   │       ├── invoice.html
│   │       ├── payslip.html
│   │       └── base.css
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_invoices.py
│   │   ├── test_payroll.py
│   │   ├── test_expenses.py
│   │   ├── test_payments.py
│   │   ├── test_exports.py
│   │   ├── test_auth.py
│   │   └── test_state_machines.py
│   ├── alembic.ini
│   ├── pyproject.toml
│   └── Dockerfile
├── cli/
│   ├── acct/
│   │   ├── __init__.py
│   │   ├── main.py                 # Typer app entry
│   │   ├── config.py               # CLI config (~/.acct/credentials.json)
│   │   ├── api_client.py           # HTTP client wrapping backend API
│   │   ├── commands/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py             # login, logout, whoami
│   │   │   ├── invoice.py
│   │   │   ├── payroll.py
│   │   │   ├── expense.py
│   │   │   ├── payment.py
│   │   │   ├── export.py
│   │   │   └── automation.py
│   │   └── formatters.py           # Table/JSON output formatting
│   ├── pyproject.toml
│   └── tests/
├── frontend/
│   ├── src/
│   │   ├── app/                    # Next.js App Router
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx            # Dashboard
│   │   │   ├── login/
│   │   │   ├── invoices/
│   │   │   ├── payroll/
│   │   │   ├── expenses/
│   │   │   ├── exports/
│   │   │   └── settings/
│   │   ├── components/
│   │   │   ├── ui/                 # Shared UI components
│   │   │   ├── invoices/
│   │   │   ├── payroll/
│   │   │   ├── expenses/
│   │   │   └── exports/
│   │   ├── lib/
│   │   │   ├── api.ts              # API client (fetch wrapper)
│   │   │   ├── auth.ts             # Token management
│   │   │   └── types.ts            # TypeScript types
│   │   └── hooks/
│   ├── package.json
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   ├── next.config.ts
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
├── intro.md
└── README.md
```

---

## 4. Data Model (Revised)

### 4.1 users

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| email | VARCHAR(255) | UNIQUE, NOT NULL |
| name | VARCHAR(255) | NOT NULL |
| password_hash | VARCHAR(255) | NOT NULL |
| is_active | BOOLEAN | DEFAULT true |
| created_at | TIMESTAMPTZ | NOT NULL |
| updated_at | TIMESTAMPTZ | NOT NULL |

### 4.2 roles

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| name | VARCHAR(100) | UNIQUE (e.g. "admin", "accountant") |
| description | TEXT | |
| is_system | BOOLEAN | DEFAULT false. true = cannot delete |

### 4.3 permissions

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| domain | VARCHAR(50) | e.g. "invoice", "payroll", "admin" |
| action | VARCHAR(50) | e.g. "read", "write", "finalize", "manage_users" |
| description | TEXT | |

**Seed data:**

```
invoice:read, invoice:write
payroll:read, payroll:write, payroll:finalize
expense:read, expense:write
payment:read, payment:write
export:read, export:write
admin:manage_users, admin:manage_roles
```

### 4.4 role_permissions (junction)

| Column | Type | Notes |
|--------|------|-------|
| role_id | UUID | FK → roles |
| permission_id | UUID | FK → permissions |

### 4.5 user_roles (junction)

| Column | Type | Notes |
|--------|------|-------|
| user_id | UUID | FK → users |
| role_id | UUID | FK → roles |

### 4.6 api_tokens (CLI long-lived tokens)

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| user_id | UUID | FK → users |
| token_hash | VARCHAR(255) | SHA-256 hash of token |
| name | VARCHAR(100) | e.g. "CLI - MacBook" |
| last_used_at | TIMESTAMPTZ | |
| expires_at | TIMESTAMPTZ | NULLABLE (null = no expiry) |
| revoked_at | TIMESTAMPTZ | NULLABLE (null = active) |
| created_at | TIMESTAMPTZ | |

### 4.7 company_settings

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK (single row) |
| legal_name | VARCHAR(255) | |
| uen | VARCHAR(50) | Singapore UEN |
| address | TEXT | |
| billing_email | VARCHAR(255) | |
| bank_name | VARCHAR(255) | |
| bank_account_number | VARCHAR(100) | |
| bank_swift_code | VARCHAR(20) | |
| logo_file_id | UUID | FK → files, NULLABLE |
| default_currency | VARCHAR(10) | FK → currencies.code |
| default_payment_terms_days | INTEGER | DEFAULT 30 |
| gst_registered | BOOLEAN | DEFAULT false |
| gst_rate | NUMERIC(5,4) | e.g. 0.0900 for 9% |
| jurisdiction | VARCHAR(20) | e.g. "SG" |
| metadata_json | JSONB | |

### 4.8 currencies

| Column | Type | Notes |
|--------|------|-------|
| code | VARCHAR(10) | PK (e.g. "SGD", "USDC") |
| name | VARCHAR(100) | e.g. "Singapore Dollar" |
| symbol | VARCHAR(10) | e.g. "$", "₩" |
| display_precision | INTEGER | SGD=2, KRW=0, USDC=2 |
| storage_precision | INTEGER | 6 for all (DB stores full precision) |
| is_crypto | BOOLEAN | DEFAULT false |
| chain_id | VARCHAR(50) | NULLABLE. e.g. "ethereum", "polygon" (crypto only) |
| is_active | BOOLEAN | DEFAULT true |

**Seed data:** SGD, USD, KRW, USDC (Ethereum), USDT (Ethereum)

### 4.9 clients

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| legal_name | VARCHAR(255) | NOT NULL |
| billing_email | VARCHAR(255) | |
| billing_address | TEXT | |
| default_currency | VARCHAR(10) | FK → currencies.code |
| payment_terms_days | INTEGER | |
| preferred_payment_method | VARCHAR(50) | "bank_transfer", "crypto" |
| wallet_address | VARCHAR(255) | NULLABLE |
| metadata_json | JSONB | |
| is_active | BOOLEAN | DEFAULT true |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

### 4.10 employees

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| name | VARCHAR(255) | NOT NULL |
| email | VARCHAR(255) | |
| base_salary | NUMERIC(19,6) | Monthly base |
| salary_currency | VARCHAR(10) | FK → currencies.code |
| start_date | DATE | Employment start |
| end_date | DATE | NULLABLE |
| work_pass_type | VARCHAR(50) | "EP", "SP", "WP", "citizen", "pr" |
| tax_residency | VARCHAR(10) | "SG", "KR", etc. |
| bank_details_json | JSONB | `{bank_name, account_number, swift}` |
| status | VARCHAR(20) | "active", "terminated" |
| metadata_json | JSONB | |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

### 4.11 invoices

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| invoice_number | VARCHAR(50) | UNIQUE, format: `INV-YYYY-NNNN` |
| client_id | UUID | FK → clients |
| issue_date | DATE | NULLABLE (set on issue) |
| due_date | DATE | NULLABLE (calculated from payment_terms) |
| currency | VARCHAR(10) | FK → currencies.code |
| subtotal_amount | NUMERIC(19,6) | Recalculated on line item mutation |
| tax_rate | NUMERIC(5,4) | NULLABLE, from company GST settings |
| tax_amount | NUMERIC(19,6) | |
| total_amount | NUMERIC(19,6) | |
| status | VARCHAR(20) | "draft", "issued", "paid", "cancelled" |
| description | TEXT | |
| payment_method | VARCHAR(50) | |
| wallet_address | VARCHAR(255) | For crypto payments |
| issued_pdf_file_id | UUID | FK → files, NULLABLE |
| recurring_rule_id | UUID | FK → recurring_invoice_rules, NULLABLE |
| idempotency_key | VARCHAR(100) | UNIQUE, NULLABLE |
| created_by | UUID | FK → users |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

### 4.12 invoice_line_items

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| invoice_id | UUID | FK → invoices |
| description | VARCHAR(500) | NOT NULL |
| quantity | NUMERIC(19,6) | |
| unit_price | NUMERIC(19,6) | |
| amount | NUMERIC(19,6) | quantity * unit_price |
| sort_order | INTEGER | |

### 4.13 recurring_invoice_rules

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| client_id | UUID | FK → clients |
| frequency | VARCHAR(20) | "monthly", "quarterly", "yearly" |
| day_of_month | INTEGER | 1-28 |
| currency | VARCHAR(10) | FK → currencies.code |
| line_items_json | JSONB | Template line items |
| payment_method | VARCHAR(50) | |
| description | TEXT | |
| is_active | BOOLEAN | DEFAULT true |
| next_issue_date | DATE | |
| last_issued_invoice_id | UUID | FK → invoices, NULLABLE |
| created_at | TIMESTAMPTZ | |

### 4.14 payroll_runs

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| employee_id | UUID | FK → employees |
| month | DATE | First day of month (e.g. 2026-03-01) |
| start_date | DATE | Actual work start (for proration) |
| end_date | DATE | Actual work end (for proration) |
| days_in_month | INTEGER | Calendar days in the month |
| days_worked | INTEGER | Calendar days worked |
| monthly_base_salary | NUMERIC(19,6) | Snapshot from employee record |
| currency | VARCHAR(10) | FK → currencies.code |
| prorated_gross_salary | NUMERIC(19,6) | |
| total_deductions | NUMERIC(19,6) | Sum of all deductions |
| net_salary | NUMERIC(19,6) | |
| status | VARCHAR(20) | "draft", "reviewed", "finalized", "paid" |
| payslip_file_id | UUID | FK → files, NULLABLE |
| paid_at | TIMESTAMPTZ | NULLABLE |
| payment_id | UUID | FK → payments, NULLABLE |
| idempotency_key | VARCHAR(100) | UNIQUE, NULLABLE |
| created_by | UUID | FK → users |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

### 4.15 payroll_deductions

범용 deduction 구조. SDL, CPF, tax withholding 등 무엇이든 추가 가능.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| payroll_run_id | UUID | FK → payroll_runs |
| deduction_type | VARCHAR(50) | "sdl", "cpf_employee", "cpf_employer", "tax" |
| description | VARCHAR(255) | |
| amount | NUMERIC(19,6) | |
| rate | NUMERIC(10,6) | NULLABLE (e.g. 0.0025 for SDL 0.25%) |
| cap_amount | NUMERIC(19,6) | NULLABLE (e.g. SDL cap) |
| metadata_json | JSONB | Jurisdiction-specific data |
| sort_order | INTEGER | |

### 4.16 expenses

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| expense_date | DATE | NOT NULL |
| vendor | VARCHAR(255) | |
| category | VARCHAR(100) | |
| currency | VARCHAR(10) | FK → currencies.code |
| amount | NUMERIC(19,6) | |
| payment_method | VARCHAR(50) | |
| reimbursable | BOOLEAN | DEFAULT false |
| status | VARCHAR(20) | "draft", "confirmed", "reimbursed" |
| notes | TEXT | |
| created_by | UUID | FK → users |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

### 4.17 payments

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| payment_type | VARCHAR(20) | "bank_transfer", "crypto" |
| related_entity_type | VARCHAR(50) | "invoice", "payroll_run", "expense" |
| related_entity_id | UUID | Polymorphic FK |
| payment_date | DATE | |
| currency | VARCHAR(10) | FK → currencies.code |
| amount | NUMERIC(19,6) | |
| fx_rate_to_sgd | NUMERIC(19,10) | NULLABLE |
| fx_rate_date | DATE | NULLABLE |
| fx_rate_source | VARCHAR(50) | "manual", "xe.com", etc. |
| sgd_value | NUMERIC(19,6) | NULLABLE |
| tx_hash | VARCHAR(255) | NULLABLE, UNIQUE WHERE NOT NULL |
| chain_id | VARCHAR(50) | NULLABLE (for crypto) |
| bank_reference | VARCHAR(255) | NULLABLE |
| proof_file_id | UUID | FK → files, NULLABLE |
| idempotency_key | VARCHAR(100) | UNIQUE, NULLABLE |
| notes | TEXT | |
| created_by | UUID | FK → users |
| created_at | TIMESTAMPTZ | |

### 4.18 files

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| storage_key | VARCHAR(500) | UUID-based, never from user input |
| original_filename | VARCHAR(255) | |
| mime_type | VARCHAR(100) | |
| size_bytes | BIGINT | Max 10MB enforced at API |
| checksum_sha256 | VARCHAR(64) | |
| uploaded_at | TIMESTAMPTZ | |
| uploaded_by | UUID | FK → users |
| linked_entity_type | VARCHAR(50) | "invoice", "payroll_run", "expense", "export_pack" |
| linked_entity_id | UUID | Polymorphic FK |

### 4.19 export_packs

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| month | DATE | First day of month |
| version | INTEGER | DEFAULT 1. (month, version) UNIQUE |
| generated_at | TIMESTAMPTZ | |
| zip_file_id | UUID | FK → files |
| manifest_json | JSONB | File list with SHA-256 checksums |
| validation_summary_json | JSONB | Completeness report |
| status | VARCHAR(20) | "generating", "complete", "failed" |
| notes | TEXT | |
| created_by | UUID | FK → users |

### 4.20 bank_transactions

Import된 은행/결제 플랫폼 원본 데이터. Payment와의 자동/수동 매칭에 사용.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| source | VARCHAR(50) | "airwallex", "dbs", "ocbc", "wise" 등 |
| source_tx_id | VARCHAR(255) | 원본 transaction ID. (source, source_tx_id) UNIQUE |
| tx_date | DATE | |
| amount | NUMERIC(19,6) | |
| currency | VARCHAR(10) | FK → currencies.code |
| counterparty | VARCHAR(255) | |
| reference | VARCHAR(255) | Bank reference / memo |
| description | TEXT | |
| matched_payment_id | UUID | FK → payments, NULLABLE |
| match_status | VARCHAR(20) | "unmatched", "auto_matched", "manual_matched", "ignored" |
| match_confidence | NUMERIC(3,2) | NULLABLE. 0.00-1.00 for auto-match |
| raw_data_json | JSONB | 원본 CSV row 전체 보존 |
| statement_file_id | UUID | FK → files (업로드된 statement 파일) |
| imported_at | TIMESTAMPTZ | |
| imported_by | UUID | FK → users |

**Auto-match 로직 (MVP):**
- 금액 + 통화 일치
- 날짜 ±3일 이내
- reference 또는 counterparty 부분 일치
- confidence score 0.8 이상만 auto_matched, 미만은 unmatched 유지

**Statement parser 플러그인 구조:**
```
statement_parsers/
├── base.py           # AbstractStatementParser
├── airwallex.py      # Airwallex CSV
├── dbs.py            # DBS bank CSV
└── generic.py        # 범용 CSV (컬럼 매핑 지정)
```

**로드맵 (MVP 이후):**
- PDF statement 파싱 (OCR / structured PDF extraction)
- Airwallex/Wise API 직접 연동 (webhook 포함)
- 실시간 auto-reconciliation

### 4.21 audit_logs

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| actor_type | VARCHAR(20) | "user", "cli", "agent", "system" |
| actor_id | UUID | FK → users (NULLABLE for system) |
| action | VARCHAR(100) | e.g. "invoice.issue", "payroll.finalize" |
| entity_type | VARCHAR(50) | |
| entity_id | UUID | |
| input_json | JSONB | |
| output_json | JSONB | |
| ip_address | VARCHAR(45) | |
| created_at | TIMESTAMPTZ | |

---

## 5. State Machines

### 5.1 Invoice States

```
draft → issued → paid
draft → cancelled
issued → cancelled  (only if no payments linked)
issued → paid
```

| Current | Action | Next | Permission | Validation |
|---------|--------|------|------------|------------|
| draft | issue | issued | invoice:write | line_items > 0, client exists, generates PDF |
| draft | cancel | cancelled | invoice:write | — |
| issued | mark_paid | paid | invoice:write | payment must be linked |
| issued | cancel | cancelled | invoice:write | no payments linked |

Invalid transitions return `409 Conflict`.

### 5.2 Payroll States

```
draft → reviewed → finalized → paid
```

| Current | Action | Next | Permission | Validation |
|---------|--------|------|------------|------------|
| draft | review | reviewed | payroll:write | deductions calculated, amounts verified |
| reviewed | finalize | finalized | payroll:finalize | generates payslip PDF |
| finalized | mark_paid | paid | payroll:write | payment_id required |

No backward transitions. Invalid transitions return `409 Conflict`.

### 5.3 Expense States

```
draft → confirmed → reimbursed
```

| Current | Action | Next | Permission | Validation |
|---------|--------|------|------------|------------|
| draft | confirm | confirmed | expense:write | — |
| confirmed | reimburse | reimbursed | expense:write | only if reimbursable=true, payment linked |

---

## 6. Jurisdiction Module

```python
# jurisdiction/base.py
class JurisdictionBase(ABC):
    @abstractmethod
    def calculate_deductions(self, gross_salary, employee) -> list[Deduction]: ...

    @abstractmethod
    def calculate_invoice_tax(self, subtotal, company_settings) -> TaxResult: ...

# jurisdiction/singapore.py
class SingaporeJurisdiction(JurisdictionBase):
    def calculate_deductions(self, gross_salary, employee):
        deductions = []
        # SDL: 0.25% of gross, capped at $11.25/month for salary ≤ $4,500
        # For salary > $4,500: 0.25% uncapped
        sdl = min(gross_salary * Decimal("0.0025"), Decimal("11.25")) \
              if gross_salary <= 4500 else gross_salary * Decimal("0.0025")
        deductions.append(Deduction(type="sdl", amount=sdl, rate=Decimal("0.0025")))

        # CPF (if applicable based on work_pass_type)
        if employee.work_pass_type in ("citizen", "pr"):
            # CPF rates based on age band and residency
            ...

        return deductions
```

### Proration Formula

Calendar-day proration (Singapore standard):

```
prorated_salary = monthly_base_salary × (days_worked / days_in_month)
```

- `days_in_month`: calendar days in the month (28/29/30/31)
- `days_worked`: from `start_date` to `end_date` inclusive, within the month
- Rounding: HALF_UP to 2 decimal places (display currency precision)

---

## 7. Auth Design

### 7.1 JWT Structure

**Access Token (Frontend):**
```json
{
  "sub": "<user_id>",
  "type": "access",
  "permissions": ["invoice:read", "invoice:write", ...],
  "exp": 900  // 15 minutes
}
```

**Refresh Token (Frontend, httpOnly cookie):**
```json
{
  "sub": "<user_id>",
  "type": "refresh",
  "jti": "<unique_id>",
  "exp": 604800  // 7 days
}
```

**API Token (CLI):**
- Stored in `api_tokens` table (hashed)
- Sent as `Authorization: Bearer <token>`
- Resolved by checking hash against `api_tokens.token_hash`
- Revocable via `revoked_at` field

### 7.2 Auth Endpoints

```
POST /api/auth/login              # email + password → access + refresh
POST /api/auth/refresh            # refresh token → new access token
POST /api/auth/logout             # invalidate refresh token
POST /api/auth/api-tokens         # create CLI token
DELETE /api/auth/api-tokens/{id}  # revoke CLI token
GET /api/auth/me                  # current user + permissions
```

### 7.3 CLI Auth Flow

```bash
acct login                  # → opens prompt, calls /api/auth/api-tokens
                            # → stores token in ~/.acct/credentials.json
acct whoami                 # → calls /api/auth/me
acct logout                 # → revokes token, deletes local file
```

### 7.4 Permission Check (FastAPI dependency)

```python
def require_permission(*perms: str):
    async def checker(current_user = Depends(get_current_user)):
        user_perms = set(current_user.permissions)
        if not all(p in user_perms for p in perms):
            raise HTTPException(403, "Insufficient permissions")
        return current_user
    return Depends(checker)

# Usage
@router.post("/invoices/{id}/issue")
async def issue_invoice(id: UUID, user=require_permission("invoice:write")):
    ...
```

---

## 8. API Design (Revised)

### 8.1 Auth

| Method | Path | Permission |
|--------|------|------------|
| POST | /api/auth/login | public |
| POST | /api/auth/refresh | public (with refresh token) |
| POST | /api/auth/logout | authenticated |
| POST | /api/auth/api-tokens | authenticated |
| DELETE | /api/auth/api-tokens/{id} | authenticated (own tokens) |
| GET | /api/auth/me | authenticated |

### 8.2 Users (admin)

| Method | Path | Permission |
|--------|------|------------|
| POST | /api/users/invite | admin:manage_users |
| GET | /api/users | admin:manage_users |
| GET | /api/users/{id} | admin:manage_users |
| PATCH | /api/users/{id} | admin:manage_users |
| POST | /api/users/{id}/roles | admin:manage_roles |
| DELETE | /api/users/{id}/roles/{role_id} | admin:manage_roles |

### 8.3 Invoices

| Method | Path | Permission |
|--------|------|------------|
| POST | /api/invoices | invoice:write |
| GET | /api/invoices | invoice:read |
| GET | /api/invoices/{id} | invoice:read |
| PATCH | /api/invoices/{id} | invoice:write (draft only) |
| POST | /api/invoices/{id}/line-items | invoice:write (draft only) |
| PATCH | /api/invoices/{id}/line-items/{item_id} | invoice:write (draft only) |
| DELETE | /api/invoices/{id}/line-items/{item_id} | invoice:write (draft only) |
| POST | /api/invoices/{id}/issue | invoice:write |
| POST | /api/invoices/{id}/mark-paid | invoice:write |
| POST | /api/invoices/{id}/cancel | invoice:write |
| POST | /api/invoices/{id}/attach-file | invoice:write |

### 8.4 Payroll

| Method | Path | Permission |
|--------|------|------------|
| POST | /api/payroll/runs | payroll:write |
| GET | /api/payroll/runs | payroll:read |
| GET | /api/payroll/runs/{id} | payroll:read |
| POST | /api/payroll/runs/{id}/review | payroll:write |
| POST | /api/payroll/runs/{id}/finalize | payroll:finalize |
| POST | /api/payroll/runs/{id}/mark-paid | payroll:write |
| POST | /api/payroll/runs/{id}/attach-file | payroll:write |

### 8.5 Employees

| Method | Path | Permission |
|--------|------|------------|
| POST | /api/employees | payroll:write |
| GET | /api/employees | payroll:read |
| GET | /api/employees/{id} | payroll:read |
| PATCH | /api/employees/{id} | payroll:write |

### 8.6 Expenses

| Method | Path | Permission |
|--------|------|------------|
| POST | /api/expenses | expense:write |
| GET | /api/expenses | expense:read |
| GET | /api/expenses/{id} | expense:read |
| PATCH | /api/expenses/{id} | expense:write |
| POST | /api/expenses/{id}/confirm | expense:write |
| POST | /api/expenses/{id}/reimburse | expense:write |
| POST | /api/expenses/{id}/attach-file | expense:write |

### 8.7 Payments

| Method | Path | Permission |
|--------|------|------------|
| POST | /api/payments | payment:write |
| GET | /api/payments | payment:read |
| GET | /api/payments/{id} | payment:read |
| POST | /api/payments/{id}/link | payment:write |

`POST /api/payments/reconcile` → MVP에서는 제거. 대신 `POST /api/payments/{id}/link`로 명시적 1:1 연결만 지원.

### 8.8 Bank Reconciliation

| Method | Path | Permission |
|--------|------|------------|
| POST | /api/bank-statements/upload | payment:write |
| GET | /api/bank-transactions | payment:read |
| GET | /api/bank-transactions/{id} | payment:read |
| POST | /api/bank-transactions/{id}/match | payment:write |
| POST | /api/bank-transactions/{id}/ignore | payment:write |
| POST | /api/bank-transactions/auto-match | payment:write |

### 8.9 Exports

| Method | Path | Permission |
|--------|------|------------|
| POST | /api/exports/month-end | export:write |
| GET | /api/exports | export:read |
| GET | /api/exports/{id} | export:read |
| GET | /api/exports/{id}/download | export:read |
| POST | /api/exports/validate/{month} | export:read |

### 8.9 Settings

| Method | Path | Permission |
|--------|------|------------|
| GET | /api/settings/company | admin:manage_users |
| PATCH | /api/settings/company | admin:manage_users |
| GET | /api/currencies | authenticated |
| POST | /api/currencies | admin:manage_users |

---

## 9. CLI Commands (Revised)

```bash
# Auth
acct login
acct logout
acct whoami

# Invoices
acct invoice create --client <id> --currency SGD
acct invoice edit <id> --description "..."
acct invoice add-item <id> --desc "Consulting" --qty 1 --price 5000
acct invoice issue <id>
acct invoice mark-paid <id> --payment-id <pid>
acct invoice cancel <id>
acct invoice list [--status draft|issued|paid|cancelled]
acct invoice show <id>
acct invoice attach <id> <filepath>

# Employees
acct employee add --name "..." --salary 9500 --currency SGD --start-date 2026-03-19 --pass-type EP
acct employee list
acct employee show <id>

# Payroll
acct payroll run --employee <id> --month 2026-03 [--start-date 2026-03-19]
acct payroll review <id>
acct payroll finalize <id>
acct payroll mark-paid <id> --payment-id <pid>
acct payroll list [--month 2026-03]
acct payroll show <id>

# Expenses
acct expense add --date 2026-03-19 --vendor "..." --category "..." --amount 100 --currency SGD
acct expense confirm <id>
acct expense reimburse <id> --payment-id <pid>
acct expense list [--month 2026-03] [--category ...]
acct expense attach <id> <filepath>

# Payments
acct payment record --type bank_transfer --entity invoice:<id> --amount 5000 --currency SGD
acct payment record --type crypto --entity payroll_run:<id> --amount 9500 --currency USDC --tx-hash 0x... --chain ethereum
acct payment list [--entity-type invoice]
acct payment show <id>

# Exports
acct export validate --month 2026-03
acct export month-end --month 2026-03 [--force]
acct export list
acct export download <id> --output ./exports/

# Automation
acct automation daily
acct automation weekly
acct automation monthly --month 2026-03

# Settings
acct settings show
acct settings update --company-name "..." --uen "..."
acct currency add --code EUR --name "Euro" --symbol "€" --precision 2
acct currency list

# Bank Reconciliation
acct bank-statement upload <filepath> --source airwallex
acct bank-statement upload <filepath> --source dbs
acct bank-tx list [--status unmatched|matched|ignored]
acct bank-tx match <tx-id> --payment-id <pid>
acct bank-tx auto-match
acct bank-tx ignore <tx-id>
```

---

## 10. Frontend Pages

### 10.1 Pages

| Path | Description | Key Components |
|------|-------------|----------------|
| `/login` | 로그인 | email/password form |
| `/` | Dashboard | KPI cards, recent activity, action items |
| `/invoices` | Invoice list | filter by status/client/month, bulk actions |
| `/invoices/[id]` | Invoice detail | line items, PDF preview, status actions, file attachments |
| `/invoices/new` | Create invoice | client select, line items editor, currency |
| `/payroll` | Payroll runs | filter by month/employee/status |
| `/payroll/[id]` | Payroll detail | salary breakdown, deductions, payslip preview |
| `/payroll/new` | Create payroll run | employee select, month, proration preview |
| `/expenses` | Expense list | filter by category/month, receipt thumbnails |
| `/expenses/new` | Add expense | form + receipt upload |
| `/exports` | Export history | month list, download, validation status |
| `/settings` | Company settings | company info, users, roles, currencies |

### 10.2 Dashboard KPIs

- Outstanding invoices (count + total amount)
- Overdue invoices (count + total amount)
- This month's payroll status (draft/reviewed/finalized/paid)
- Pending expenses (unconfirmed count)
- Missing evidence count
- Latest export pack status

---

## 11. Automation Commands

### 11.1 Daily (`acct automation daily`)

Output: JSON/Markdown report

Checks:
- Overdue invoices (issued + past due_date)
- Unpaid payroll runs (finalized but not paid)
- Expenses without receipts (confirmed but no file attached)
- Unlinked payments (no related_entity)

### 11.2 Weekly (`acct automation weekly`)

Output: JSON/Markdown report

Checks:
- Invoice aging report (0-30, 30-60, 60-90, 90+ days)
- This week's expenses summary by category
- Outstanding client payments
- Missing evidence reminder

### 11.3 Monthly (`acct automation monthly --month 2026-03`)

Actions:
- Generate recurring invoices from `recurring_invoice_rules`
- Create payroll run drafts for active employees
- Run export validation for the month
- Generate month-end export pack (if validation passes)

---

## 12. Export Pack Format

```
export-2026-03-v1/
├── manifest.json
├── invoices/
│   ├── summary.csv
│   ├── INV-2026-0001.pdf
│   └── INV-2026-0002.pdf
├── payroll/
│   ├── summary.csv
│   └── payslip-2026-03-employee-name.pdf
├── expenses/
│   ├── summary.csv
│   └── receipts/
│       ├── receipt-001.jpg
│       └── receipt-002.pdf
├── payments/
│   └── summary.csv
└── evidence/
    ├── bank-proof-001.pdf
    └── tx-proof-001.png
```

### manifest.json

```json
{
  "month": "2026-03",
  "version": 1,
  "generated_at": "2026-04-01T10:00:00Z",
  "generated_by": "user@company.com",
  "company": { "name": "...", "uen": "..." },
  "summary": {
    "total_invoices": 2,
    "total_invoice_amount": { "SGD": 15000.00, "USD": 5000.00 },
    "total_payroll_runs": 1,
    "total_payroll_amount": { "SGD": 9500.00 },
    "total_expenses": 5,
    "total_expense_amount": { "SGD": 1200.00 },
    "total_payments": 3
  },
  "files": [
    { "path": "invoices/INV-2026-0001.pdf", "sha256": "abc123..." },
    ...
  ],
  "validation": {
    "all_invoices_issued_or_paid": true,
    "all_payroll_finalized_or_paid": true,
    "all_expenses_confirmed": false,
    "missing_evidence": ["expense-003"]
  }
}
```

---

## 13. Agent Skills Response Envelope

모든 skill은 통일된 응답 구조:

```json
{
  "success": true,
  "data": { ... },
  "error": null
}
```

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "INVALID_STATE_TRANSITION",
    "message": "Cannot issue invoice in 'cancelled' state",
    "details": { "current_status": "cancelled", "attempted_action": "issue" }
  }
}
```

---

## 14. Docker Compose

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: backoffice
      POSTGRES_USER: backoffice
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: ${MINIO_ACCESS_KEY}
      MINIO_ROOT_PASSWORD: ${MINIO_SECRET_KEY}
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - minio_data:/data

  backend:
    build: ./backend
    environment:
      DATABASE_URL: postgresql+asyncpg://backoffice:${DB_PASSWORD}@db:5432/backoffice
      S3_ENDPOINT: http://minio:9000
      S3_ACCESS_KEY: ${MINIO_ACCESS_KEY}
      S3_SECRET_KEY: ${MINIO_SECRET_KEY}
      S3_BUCKET: backoffice
      JWT_SECRET: ${JWT_SECRET}
      SUPERADMIN_EMAIL: ${SUPERADMIN_EMAIL}
      SUPERADMIN_PASSWORD: ${SUPERADMIN_PASSWORD}
    ports:
      - "8000:8000"
    depends_on:
      - db
      - minio

  frontend:
    build: ./frontend
    environment:
      NEXT_PUBLIC_API_URL: http://localhost:8000
    ports:
      - "3000:3000"
    depends_on:
      - backend

volumes:
  pgdata:
  minio_data:
```

---

## 15. Implementation Phases

### Phase 1: Foundation (DB + Auth + Core Models)

**Steps:**

1. **Project scaffolding**
   - `backend/`: FastAPI project with pyproject.toml, Dockerfile
   - `cli/`: Typer project with pyproject.toml
   - `frontend/`: Next.js project
   - `docker-compose.yml` + `.env.example`

2. **Database setup**
   - SQLAlchemy models for all tables in Section 4
   - Alembic initial migration
   - Seed data: currencies, default permissions, default roles (superadmin, admin, accountant, viewer)

3. **Auth system**
   - User model + password hashing (bcrypt)
   - JWT access/refresh token generation
   - API token CRUD + hash verification
   - Permission check middleware
   - `POST /api/auth/login`, `/refresh`, `/logout`, `/api-tokens`, `/me`
   - First-run superadmin creation from env vars

4. **User management**
   - Invite endpoint (creates user with temp password)
   - Role assignment
   - RBAC enforcement on all subsequent endpoints

5. **Company settings**
   - CRUD for company_settings (single row)
   - Currency CRUD

6. **File storage service**
   - Upload to MinIO (UUID-based keys)
   - Download with presigned URLs
   - SHA-256 checksum on upload
   - 10MB size limit

7. **Audit log middleware**
   - Automatic audit logging on state-changing endpoints

**Acceptance Criteria:**
- [ ] `docker-compose up` starts all services
- [ ] Superadmin can login via API and get JWT
- [ ] RBAC blocks unauthorized access (test: viewer cannot POST /api/invoices)
- [ ] File upload/download works via MinIO
- [ ] Audit log records all state-changing actions
- [ ] Alembic migration runs cleanly on fresh DB

### Phase 2: Invoice Domain

**Steps:**

1. **Client CRUD** — create, list, get, update clients
2. **Invoice CRUD** — create draft, edit draft, add/edit/delete line items
3. **Invoice state machine** — issue, mark-paid, cancel with validation
4. **Invoice number generation** — `INV-YYYY-NNNN` format, sequential per year
5. **Subtotal recalculation** — on every line item mutation
6. **Tax calculation** — from company_settings GST rate (if registered)
7. **Invoice PDF generation** — Jinja2 template + WeasyPrint
8. **Recurring invoice rules** — CRUD + template storage
9. **CLI commands** — invoice create, edit, add-item, issue, mark-paid, cancel, list, show, attach
10. **Tests** — state machine transitions (valid + invalid), PDF generation, idempotency

**Acceptance Criteria:**
- [ ] Create invoice with line items, issue it, get PDF
- [ ] `POST /api/invoices/{id}/issue` twice returns same result (idempotent)
- [ ] Cancel blocked if payment is linked
- [ ] Draft edit works; issued edit returns 409
- [ ] Invoice number is sequential: INV-2026-0001, INV-2026-0002
- [ ] CLI `acct invoice create` → `acct invoice issue` → PDF generated

### Phase 3: Payroll Domain

**Steps:**

1. **Employee CRUD** — add, list, get, update employees
2. **Payroll run creation** — with proration calculation
3. **Jurisdiction module** — Singapore SDL calculation
4. **Payroll deductions** — generic deduction records
5. **Payroll state machine** — draft → reviewed → finalized → paid
6. **Payslip PDF generation** — salary breakdown + deductions
7. **CLI commands** — employee add, payroll run, review, finalize, mark-paid
8. **Tests** — proration formula, SDL calculation, state transitions

**Acceptance Criteria:**
- [ ] Payroll run for EP holder with start_date=2026-03-19, salary=9500 → correct proration
  - days_worked=13 (Mar 19-31), days_in_month=31
  - prorated = 9500 × 13/31 = 3983.87
  - SDL = 3983.87 × 0.0025 = 9.96
  - net = 3983.87 - 9.96 = 3973.91
- [ ] Finalize generates payslip PDF
- [ ] mark-paid requires payment_id
- [ ] Invalid transitions return 409

### Phase 4: Expense + Payment Domains

**Steps:**

1. **Expense CRUD** — add, list, get, update, confirm, reimburse
2. **Expense state machine** — draft → confirmed → reimbursed
3. **Payment recording** — bank_transfer + crypto with metadata
4. **Payment linking** — explicit 1:1 link to invoice/payroll/expense
5. **Cross-currency validation** — warn on currency mismatch
6. **Duplicate payment prevention** — tx_hash uniqueness, idempotency key
7. **Bank statement import** — CSV upload + parsing (Airwallex, DBS, generic)
8. **Statement parser plugin system** — AbstractStatementParser + concrete parsers
9. **Auto-match engine** — amount + currency + date ±3d + reference matching
10. **Manual match + ignore** — UI/CLI for unmatched transactions
11. **CLI commands** — expense, payment, bank-statement, bank-tx commands
12. **Tests** — duplicate tx_hash, currency mismatch, auto-match logic, parser correctness

**Acceptance Criteria:**
- [ ] Record crypto payment with tx_hash + chain_id
- [ ] Duplicate tx_hash returns 409
- [ ] Payment linked to invoice transitions invoice to paid
- [ ] Expense reimburse blocked if reimbursable=false
- [ ] FX rate stored with date and source
- [ ] Upload Airwallex CSV → bank_transactions populated with correct fields
- [ ] Auto-match correctly links transaction to payment (amount + currency + date match)
- [ ] Auto-match does NOT link when confidence < 0.8
- [ ] (source, source_tx_id) unique constraint prevents duplicate import
- [ ] Manual match via CLI and API works

### Phase 5: Export + Automation

**Steps:**

1. **Export validation** — completeness check for a month
2. **Export pack generation** — ZIP with CSVs + PDFs + manifest
3. **Generic CSV formatter** — pluggable formatter base class
4. **Export versioning** — (month, version) unique
5. **Daily automation** — overdue/missing evidence checks
6. **Weekly automation** — aging report, expense summary
7. **Monthly automation** — recurring invoice generation, payroll draft creation, export
8. **CLI commands** — export validate/month-end/list/download, automation daily/weekly/monthly
9. **Tests** — export completeness, manifest integrity, automation outputs

**Acceptance Criteria:**
- [ ] `acct export validate --month 2026-03` shows completeness report
- [ ] `acct export month-end --month 2026-03` generates ZIP with correct structure
- [ ] Manifest SHA-256 checksums match actual files
- [ ] `--force` flag exports even with incomplete data
- [ ] Monthly automation creates recurring invoices and payroll drafts
- [ ] Export version increments on re-generation

### Phase 6: Frontend

**Steps:**

1. **Auth flow** — login page, token management, protected routes
2. **Dashboard** — KPI cards, recent activity, action items
3. **Invoice pages** — list, detail, create, PDF preview, status actions
4. **Payroll pages** — list, detail, create, payslip preview
5. **Expense pages** — list, create, receipt upload/preview
6. **Export pages** — list, generate, download, validation status
7. **Settings pages** — company info, user management, role management, currencies

**Acceptance Criteria:**
- [ ] Login → Dashboard → Navigate all domains
- [ ] Create invoice with line items in UI
- [ ] Issue invoice and preview PDF in browser
- [ ] Create payroll run and see proration breakdown
- [ ] Upload receipt for expense
- [ ] Generate and download export pack
- [ ] Admin can invite users and assign roles

---

## 16. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| WeasyPrint Docker compatibility | PDF generation fails in container | Test WeasyPrint in `python:3.12-slim` early in Phase 1 scaffolding |
| Polymorphic FK (payments, files) | No DB-level referential integrity | Application-level validation in service layer + integration tests |
| Multi-currency rounding | Silent precision loss | NUMERIC(19,6) storage + per-currency display_precision + round-trip tests |
| JWT token leakage (CLI) | Unauthorized access | api_tokens.revoked_at + `~/.acct/credentials.json` with 0600 permissions |
| State machine race conditions | Concurrent transitions corrupt state | SELECT FOR UPDATE on status transitions + idempotency keys |
| Large export packs | Memory/timeout issues | Stream ZIP generation, chunk file reads |

---

## 17. Verification Steps

After full implementation:

1. **E2E Invoice flow**: create client → create invoice → add items → issue → PDF generated → record payment → mark paid → verify audit log
2. **E2E Payroll flow**: add employee → create run → review → finalize → payslip PDF → record payment → mark paid
3. **E2E Export flow**: complete a month's invoices + payroll + expenses → validate → export → verify ZIP structure + manifest checksums
4. **RBAC enforcement**: login as viewer → verify all write endpoints return 403
5. **CLI parity**: every API action is achievable via CLI
6. **Idempotency**: issue/finalize/export same entity twice → no side effects
7. **Docker fresh start**: `docker-compose down -v && docker-compose up` → migrate → seed → full flow works
