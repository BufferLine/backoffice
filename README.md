# Bufferline Backoffice

Backoffice operations system for Singapore-based small companies. Automates invoice, payroll, expense, payment tracking, and month-end accountant handoff.

## What It Does

- **Invoices**: Create, issue, track payment, generate PDF with company stamp
- **Payroll**: Prorated salary calculation, Singapore SDL/CPF, payslip PDF
- **Expenses**: Record, categorize, attach receipts, reimburse
- **Payments**: Bank transfer & crypto, link to invoices/payroll, FX tracking
- **Bank Reconciliation**: Import CSV statements, auto-match transactions
- **Accounts**: Track balances across bank/crypto/cash accounts
- **Exports**: Monthly ZIP pack with CSVs + PDFs + manifest for accountant
- **Compliance**: Singapore task calendar (SDL, CPF, GST, IR8A deadlines)
- **Audit**: Full audit log + field-level change tracking

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.12+
- Node.js 20+ (for frontend, optional)

### Setup

```bash
# Clone and enter the project
cd backoffice

# Copy environment file
cp .env.example .env

# Full reset (starts Docker, creates DB, runs migrations, starts server)
scripts/reset.sh
```

### Onboarding

```bash
# Initialize your company (interactive or with flags)
acct init --company-name "Your Company Pte Ltd" --jurisdiction SG

# Open the printed URL in your browser to create your admin account
# Then:
acct login --email your@email.com --password yourpassword
```

### Daily Usage

```bash
# Clients
acct client create --name "Acme Corp" --currency SGD
acct client list

# Invoices
acct invoice create --client <client-id> --currency SGD
acct invoice add-item <invoice-id> --desc "Consulting" --qty 160 --price 31.25
acct invoice issue <invoice-id>          # → generates PDF

# Payroll
acct employee add --name "John Doe" --salary 9500 --start-date 2026-03-19 --pass-type EP
acct payroll run --employee <id> --month 2026-03 --start-date 2026-03-19
acct payroll review <id>
acct payroll finalize <id>               # → generates payslip PDF

# Expenses
acct expense add --date 2026-03-15 --vendor AWS --category cloud --amount 145 --currency USD
acct expense confirm <id>

# Payments
acct payment record --type bank_transfer --entity invoice:<id> --amount 5000 --currency SGD --date 2026-03-20

# Accounts & Balance
acct account create --name "DBS SGD" --type bank --currency SGD --opening-balance 50000 --opening-balance-date 2026-03-01
acct account balance <id>

# Monthly compliance
acct todo summary                        # What's due this month
acct automation monthly --month 2026-03  # Auto-generate recurring invoices + payroll drafts

# Export for accountant
acct export validate --month 2026-03
acct export month-end --month 2026-03    # → ZIP with CSVs + PDFs + manifest
```

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌──────────────┐
│   CLI (acct) │────→│  FastAPI     │────→│  PostgreSQL   │
│   Typer      │     │  Backend     │     │  16           │
└─────────────┘     │              │     └──────────────┘
                    │  Services    │     ┌──────────────┐
┌─────────────┐     │  Models      │────→│  MinIO (S3)   │
│  Frontend    │────→│  State Mach. │     │  PDFs/Files   │
│  Next.js     │     │  Jurisdiction│     └──────────────┘
└─────────────┘     └─────────────┘
```

### Key Modules

| Module | Description |
|--------|-------------|
| `api/` | REST endpoints with RBAC |
| `models/` | 30 SQLAlchemy models |
| `services/` | Business logic (invoice, payroll, payment, export, etc.) |
| `state_machines/` | Transition validation (draft→issued→paid) |
| `jurisdiction/` | Country-specific tax rules (SG: SDL, CPF, GST) |
| `statement_parsers/` | Bank CSV parsers (Airwallex, DBS, generic) |
| `export_formatters/` | Pluggable export formats (generic CSV, extensible) |

## Testing

```bash
scripts/test.sh           # 163 unit/integration tests (pytest)
scripts/e2e.sh            # 31 API-level E2E checks
scripts/e2e-cli.sh        # 36 CLI E2E checks (full business workflow)
```

## Scripts

| Script | Description |
|--------|-------------|
| `scripts/reset.sh` | Full reset: Docker + DB + migrations + server |
| `scripts/dev.sh` | Start dev server (preserves data) |
| `scripts/stop.sh` | Stop all services |
| `scripts/test.sh` | Run pytest |
| `scripts/e2e.sh` | API E2E test |
| `scripts/e2e-cli.sh` | CLI E2E test |
| `scripts/seed-demo.sh` | Seed demo data |

## Singapore Compliance

Built-in support for:
- **SDL** (Skills Development Levy): 0.25%, capped at $11.25 for salary ≤ $4,500
- **CPF** (Central Provident Fund): citizen/PR rates
- **GST**: 9%, inclusive or exclusive pricing
- **Salary proration**: Calendar-day method
- **Compliance calendar**: SDL/CPF payment (14th), GST filing (quarterly), IR8A (annual)

## Design Principles

1. **Boring Core, Agentic UX** — deterministic backend, agent-friendly API
2. **Evidence First** — every financial action has proof attached
3. **Export First** — accountant handoff quality over UI polish
4. **Idempotent Operations** — safe to retry any command
5. **CLI First** — everything works without a browser

## License

Private — Bufferline Pte Ltd
