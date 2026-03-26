# Architecture

System design, data model, and key subsystems.

## Design Principles

1. **Boring Core, Agentic UX** — deterministic backend, agent-friendly CLI/API surface
2. **Evidence First** — every financial action has proof attached (PDF, receipt, tx hash)
3. **Export First** — accountant handoff quality over UI polish
4. **Idempotent Operations** — `issue`, `finalize`, `export` are safe to retry
5. **CLI First** — all operations work without a browser
6. **Audit Everything** — who, when, what input, what state change

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Clients                                  │
│  acct CLI (Typer)    Browser (Next.js)    AI Agent / scripts     │
└──────────┬──────────────────┬────────────────────┬──────────────┘
           │                  │                    │
           └──────────────────┼────────────────────┘
                              │ HTTP / REST
                    ┌─────────▼──────────┐
                    │   FastAPI Backend   │
                    │                    │
                    │  ┌──────────────┐  │
                    │  │  API Layer   │  │  ~152 endpoints
                    │  │  (RBAC)      │  │
                    │  └──────┬───────┘  │
                    │  ┌──────▼───────┐  │
                    │  │  Services    │  │  Business logic
                    │  └──────┬───────┘  │
                    │  ┌──────▼───────┐  │
                    │  │State Machines│  │  Transition validation
                    │  └──────┬───────┘  │
                    │  ┌──────▼───────┐  │
                    │  │  Models      │  │  SQLAlchemy ORM
                    │  └──────┬───────┘  │
                    └─────────┼──────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
   ┌──────────▼──────────┐       ┌────────────▼──────────┐
   │    PostgreSQL 16     │       │   Object Storage       │
   │  (Supabase / local)  │       │  (R2 / MinIO)          │
   │   37 tables          │       │  PDFs, receipts,       │
   └─────────────────────┘       │  export ZIPs           │
                                  └────────────────────────┘
```

---

## Component Overview

### Backend (`backend/`)

Python 3.12 + FastAPI + SQLAlchemy 2.0 (async). The system of record. All validation, state transitions, calculations, and document generation happen here.

Key modules:

| Module | Description |
|--------|-------------|
| `api/` | REST endpoints with RBAC decorators (~152 endpoints) |
| `models/` | SQLAlchemy models (37 tables) |
| `schemas/` | Pydantic request/response schemas |
| `services/` | Business logic (invoice, payroll, export, etc.) |
| `state_machines/` | Transition validation (draft → issued → paid) |
| `jurisdiction/` | Country-specific tax rules (Singapore: SDL, CPF, GST) |
| `statement_parsers/` | Bank CSV parsers (DBS, Airwallex, generic) |
| `export_formatters/` | Pluggable export formats (generic CSV, extensible) |
| `templates/` | Jinja2 HTML templates for invoice and payslip PDFs |

### CLI (`cli/`)

Python Typer + httpx + Rich. The primary execution interface for operators and AI agents. Every backend operation is reachable via `acct <domain> <command>`.

### Frontend (`frontend/`)

Next.js 16.2.0 + TypeScript + Tailwind. Thin dashboard: list, detail, approve, attach, export. Not the primary interface — the CLI is.

### Storage

- **Relational**: PostgreSQL 16 for all metadata, state, and financial data
- **Object**: S3-compatible storage for PDFs, receipts, export ZIPs

---

## Data Model

37 tables grouped by domain.

### Identity & Config

| Table | Description |
|-------|-------------|
| `users` | Admin and operator accounts |
| `roles` | Named roles for RBAC |
| `permissions` | Domain-scoped permission strings |
| `role_permissions` | Join table: roles ↔ permissions |
| `user_roles` | Join table: users ↔ roles |
| `api_tokens` | Long-lived API tokens for CLI/agent access |
| `company_settings` | Company profile, branding, GST, bank details |
| `currencies` | Supported currencies with symbol and precision |
| `setup_tokens` | One-time setup URLs (expire after 1 hour) |

### Clients & Employees

| Table | Description |
|-------|-------------|
| `clients` | Billing clients with payment terms |
| `employees` | Employee records with salary and pass type |

### Invoices

| Table | Description |
|-------|-------------|
| `invoices` | Invoice header (status, totals, dates) |
| `invoice_line_items` | Line items with per-item tax code and rate |
| `invoice_payment_methods` | Join table for multi-payment-method invoices |
| `recurring_invoice_rules` | Recurring invoice schedules |

### Payroll

| Table | Description |
|-------|-------------|
| `payroll_runs` | Monthly payroll runs with SDL, CPF, net salary |
| `payroll_deductions` | Per-run deduction line items (CPF, SDL, custom) |

### Loans

| Table | Description |
|-------|-------------|
| `loans` | Director/shareholder loan records (principal, rate, status) |
| `payment_allocations` | Allocations of payments to loan repayments |

### Expenses

| Table | Description |
|-------|-------------|
| `expenses` | Expense records with category and reimbursement status |

### Payments

| Table | Description |
|-------|-------------|
| `payments` | Payment records (bank, crypto, cash) linked to any entity |
| `payment_methods` | Registered payment methods (bank, PayNow, crypto) |

### Accounts & Transactions

| Table | Description |
|-------|-------------|
| `accounts` | Bank, crypto wallet, cash, or virtual accounts with account_class (asset/liability/equity/revenue/expense) |
| `journal_entries` | General ledger entries with entry_date, description, source_type, source_id, is_confirmed, confirmed_at/by |
| `journal_lines` | Individual debit/credit lines per journal entry; balance derived from confirmed lines (CHECK: debit xor credit) |
| `transactions` | Ledger entries (in/out) with status |
| `bank_transactions` | Imported bank statement rows |
| `recurring_commitments` | Scheduled recurring transactions |

### Exports & Files

| Table | Description |
|-------|-------------|
| `export_packs` | Month-end export records with ZIP file reference |
| `files` | Object storage metadata (key, mime type, checksum) |

### Tasks & Audit

| Table | Description |
|-------|-------------|
| `task_templates` | Recurring task definitions (SDL due 14th, etc.) |
| `task_instances` | Generated task instances per period |
| `audit_logs` | Every state-changing API call (actor, input, output) |
| `change_logs` | Field-level diffs on all entity updates |

### Integrations

| Table | Description |
|-------|-------------|
| `integration_events` | Webhook/sync event log with idempotency |
| `integration_sync_states` | Sync progress per provider per account |
| `integration_configs` | Runtime config (OAuth tokens, tenant IDs, encrypted) |

---

## State Machines

State transitions are validated server-side. Invalid transitions return HTTP 409.

### Invoice

```
draft ──issue──→ issued ──mark_paid──→ paid
  │                 │
  └──cancel──→ cancelled ←──cancel──┘
```

| Action | From | To |
|--------|------|----|
| `issue` | draft | issued |
| `mark_paid` | issued | paid |
| `cancel` | draft or issued | cancelled |

### Payroll

```
draft ──review──→ reviewed ──finalize──→ finalized ──mark_paid──→ paid
```

| Action | From | To |
|--------|------|----|
| `review` | draft | reviewed |
| `finalize` | reviewed | finalized |
| `mark_paid` | finalized | paid |

### Expense

```
draft ──confirm──→ confirmed ──reimburse──→ reimbursed
```

| Action | From | To |
|--------|------|----|
| `confirm` | draft | confirmed |
| `reimburse` | confirmed | reimbursed |

---

## Database Security & Accounting Model

**Row Level Security (RLS)** is enabled on all public schema tables to enforce tenant isolation and multi-user access control at the database layer.

**Account Balances** are calculated dynamically from confirmed journal lines using debit-normal (asset, expense) or credit-normal (liability, equity, revenue) conventions:
- Assets/Expenses: balance = sum(debits) - sum(credits)
- Liabilities/Equity/Revenue: balance = sum(credits) - sum(debits)

Journal entries must be explicitly confirmed before impacting account balances.

---

## Auth & RBAC

JWT-based authentication. Permissions are domain-scoped strings:

```
invoice:read      invoice:write     invoice:finalize
payroll:read      payroll:write     payroll:finalize
expense:read      expense:write
payment:read      payment:write
export:read       export:write
settings:read     settings:write
```

The admin user has all permissions. Additional users can be scoped to specific domains (e.g. a read-only accountant role).

---

## Jurisdiction Module

Located in `backend/app/jurisdiction/`. Each jurisdiction is a class implementing:

- `calculate_sdl(gross_salary)` — Skills Development Levy
- `calculate_cpf(gross_salary, pass_type)` — CPF contributions
- `get_tax_rate()` — Default GST/VAT rate
- `get_compliance_tasks(month)` — Monthly compliance task list

### Singapore (`jurisdiction/singapore.py`)

- **SDL**: 0.25% of gross salary, capped at SGD 11.25 for salary ≤ SGD 4,500
- **CPF**: Citizen/PR rates by age band (employer + employee contributions)
- **GST**: 9%, per-line-item tax codes (SR / ZR / ES / NT)
- **Compliance calendar**: SDL/CPF payment by 14th, quarterly GST filing, annual IR8A

New jurisdictions: create a new file in `jurisdiction/`, implement the base class from `jurisdiction/base.py`, and register it in the jurisdiction factory.

---

## PDF Generation Pipeline

1. Invoice or payroll run is finalized via API
2. Service fetches company settings (logo, stamp, colors, bank details)
3. Jinja2 template in `templates/` is rendered with entity data
4. WeasyPrint converts HTML+CSS to PDF
5. PDF is uploaded to object storage via `files` service
6. `files.id` is stored on the entity (`issued_pdf_file_id`, `payslip_file_id`)
7. Download endpoint streams the file from object storage

Templates support: company logo, stamp image, PayNow QR code, GST breakdown by rate, custom colors and font family.

Document types: invoice, payslip, loan agreement, loan statement, loan discharge letter.

---

## Export Pack Structure

Month-end export packs are ZIP files with a predictable layout:

```
export-2026-03/
  manifest.json           # Summary: counts, totals, file list, validation status
  invoices/
    invoices.csv          # All invoices for the month
    INV-2026-001.pdf
    INV-2026-002.pdf
    ...
  payroll/
    payroll_runs.csv      # All payroll runs
    payslip-<id>.pdf
    ...
  expenses/
    expenses.csv          # All expenses
    receipts/
      receipt-<id>.pdf
      ...
  payments/
    payments.csv          # All payment records
  accounts/
    transactions.csv      # Ledger transactions
```

The manifest includes:
- Period, generated timestamp
- Count and total for each domain
- Validation status (any missing evidence or unconfirmed items)
- SHA256 checksums for all included files

Export packs are immutable once generated. Regenerating creates a new version.
