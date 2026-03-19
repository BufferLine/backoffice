# Backoffice Operations System

## Quick Start

```bash
scripts/reset.sh          # Full reset: docker + DB + migrations + server
scripts/dev.sh            # Start dev server (keeps data)
scripts/stop.sh           # Stop everything
```

## Onboarding (first run after reset)

```bash
acct init --company-name "Company Name" --jurisdiction SG --api-url http://localhost:8000
# → open the printed URL in browser to create admin account
acct login --email admin@company.com --password <password>
```

## Testing

```bash
scripts/test.sh           # 163 pytest unit/integration tests
scripts/e2e.sh            # 31 API E2E checks
scripts/e2e-cli.sh        # 36 CLI E2E checks (full workflow)
```

## Project Structure

```
backend/                  # Python FastAPI + SQLAlchemy
  app/
    api/                  # REST endpoints (~95 endpoints)
    models/               # SQLAlchemy models (30 tables)
    schemas/              # Pydantic request/response schemas
    services/             # Business logic
    state_machines/       # Invoice, payroll, expense state transitions
    jurisdiction/         # SG tax/deduction rules (modular)
    export_formatters/    # Pluggable CSV/export formatters
    statement_parsers/    # Bank statement CSV parsers
    templates/            # Invoice/payslip PDF templates (Jinja2)
  alembic/                # DB migrations
  tests/                  # pytest tests
cli/                      # Python Typer CLI (`acct` command)
  acct/commands/          # All CLI subcommands
frontend/                 # Next.js 15 (placeholder pages + login + setup)
scripts/                  # Dev/test/deploy scripts
```

## Tech Stack

- Backend: Python 3.12, FastAPI, SQLAlchemy 2.0 (async), PostgreSQL 16
- CLI: Typer + httpx + Rich
- PDF: Jinja2 + WeasyPrint
- Storage: MinIO (S3-compatible)
- Frontend: Next.js 15, TypeScript, Tailwind CSS
- Infra: Docker Compose

## Key Design Decisions

- **CLI-first**: all operations available via `acct` CLI
- **Domain-based RBAC**: permissions like `invoice:write`, `payroll:finalize`
- **State machines**: invoice (draft→issued→paid/cancelled), payroll (draft→reviewed→finalized→paid), expense (draft→confirmed→reimbursed)
- **Jurisdiction module**: Singapore SDL/CPF/GST calculations, extensible for other countries
- **Single-entry cash ledger**: not double-entry bookkeeping (accountant handles that)
- **Evidence-first**: every financial action produces proof (PDF, receipt, tx hash)

## Environment Variables

See `.env.example`. Key vars:
- `DB_PASSWORD` — PostgreSQL password
- `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` — S3 storage
- `JWT_SECRET` — JWT signing key

## Conventions

- Money fields: `NUMERIC(19,6)` in DB, `Decimal` in Python
- Timestamps: `TIMESTAMP(timezone=True)` (not TIMESTAMPTZ)
- UUIDs for all primary keys
- API returns 409 on invalid state transitions
- Audit log on all state-changing operations
- Change log tracks field-level diffs
