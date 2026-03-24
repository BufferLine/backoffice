# Backoffice Operations System

## Quick Start

```bash
scripts/reset.sh          # Full reset: docker + DB + migrations + server
scripts/dev.sh            # Start dev server (keeps data)
scripts/stop.sh           # Stop everything
```

## Onboarding (first run after reset)

```bash
acct init --api-url http://localhost:8000
# → prompts for company name, jurisdiction, UEN
# → open the printed URL in browser to create admin account
acct login --email admin@company.com --api-url http://localhost:8000
# → prompts for password
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
    models/               # SQLAlchemy models (31 tables)
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

## Agent Usage (for Claude Code / AI agents)

### Install CLI
pip install "git+https://github.com/YOUR_ORG/backoffice.git#subdirectory=cli"

### Login
acct login --email admin@example.com --api-url https://backoffice.yourdomain.com

### Monthly Workflow
1. acct todo summary → check this month's tasks
2. Process each todo in order
3. acct automation monthly --month YYYY-MM
4. acct export month-end --month YYYY-MM

### Common Operations
- acct invoice create/issue/download
- acct payroll run/review/finalize/download
- acct expense add/confirm
- acct payment record
- acct todo complete <id>

## Roadmap

See `ROADMAP.md` for the full feature roadmap and integration phases. Check it before starting new work to pick the next task.

## Environment Variables

See `.env.example`. Key vars:
- `DB_PASSWORD` — PostgreSQL password (local dev only)
- `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` — S3 storage (local dev only)
- `JWT_SECRET` — JWT signing key
- `DATABASE_URL` — full DB connection string (production)
- `S3_ENDPOINT` / `S3_ACCESS_KEY` / `S3_SECRET_KEY` / `S3_REGION` — storage (production)
- `API_BASE_URL` — external URL used in setup links
- `CORS_ORIGINS` — comma-separated allowed origins

## Git Workflow

- **Never push directly to main** — always create a feature branch and open a PR
- Branch naming: `feat/`, `fix/`, `refactor/`, `test/` + short description (e.g., `feat/airwallex-fx-rate`)
- Merge only after review/approval
- Commit messages: conventional commits (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`)

## Language

- All code, comments, commit messages, PR descriptions, and documentation must be written in **English**

## Conventions

- Money fields: `NUMERIC(19,6)` in DB, `Decimal` in Python
- Timestamps: `TIMESTAMP(timezone=True)` (not TIMESTAMPTZ)
- UUIDs for all primary keys
- API returns 409 on invalid state transitions
- Audit log on all state-changing operations
- Change log tracks field-level diffs
