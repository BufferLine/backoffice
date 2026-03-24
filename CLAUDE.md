# Backoffice Operations System

Singapore-based backoffice for invoicing, payroll, expenses, payments, and bank reconciliation.

## Quick Start

```bash
scripts/reset.sh          # Full reset: docker + DB + migrations + server
scripts/dev.sh            # Start dev server (keeps data)
scripts/stop.sh           # Stop everything
```

## Testing

```bash
scripts/ci.sh             # Full CI pipeline (unit + API E2E + CLI E2E)
```

Quick unit tests only (no server needed):
```bash
python -m pytest backend/tests/unit/ -v
```

See [docs/testing.md](docs/testing.md) for test tiers, writing guide, and pre-PR checklist.

## Project Structure

```
backend/app/              # Python FastAPI + SQLAlchemy
  api/                    # REST endpoints (~95 endpoints)
  models/                 # SQLAlchemy models (31 tables)
  schemas/                # Pydantic request/response schemas
  services/               # Business logic
  state_machines/         # Invoice, payroll, expense state transitions
  jurisdiction/           # SG tax/deduction rules (modular)
  integrations/           # Provider framework (Airwallex, etc.)
  statement_parsers/      # Bank statement CSV parsers
  templates/              # Invoice/payslip PDF templates (Jinja2)
cli/acct/                 # Python Typer CLI (`acct` command)
frontend/                 # Next.js 15
scripts/                  # Dev/test/deploy scripts
```

## Key Design Decisions

- **CLI-first**: all operations available via `acct` CLI
- **Domain-based RBAC**: permissions like `invoice:write`, `payroll:finalize`
- **State machines**: invoice (draft→issued→paid/cancelled), payroll (draft→reviewed→finalized→paid), expense (draft→confirmed→reimbursed)
- **Jurisdiction module**: Singapore SDL/CPF/GST calculations, extensible
- **Evidence-first**: every financial action produces proof (PDF, receipt, tx hash)

## Git Workflow

- **Never push directly to main** — always create a feature branch and open a PR
- Branch naming: `feat/`, `fix/`, `refactor/`, `test/` + short description
- Run `scripts/ci.sh` before opening a PR
- Commit messages: conventional commits (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`)

## Language

- All code, comments, commit messages, PR descriptions, and documentation must be written in **English**

## Conventions

- Money: `NUMERIC(19,6)` in DB, `Decimal` in Python — never `float`
- Timestamps: `TIMESTAMP(timezone=True)`
- UUIDs for all primary keys
- API returns 409 on invalid state transitions
- Audit log on all state-changing operations
- Change log tracks field-level diffs

## Detailed Documentation

| Topic | Location |
|-------|----------|
| Development setup | [docs/development.md](docs/development.md) |
| Testing & CI | [docs/testing.md](docs/testing.md) |
| Architecture | [docs/architecture.md](docs/architecture.md) |
| CLI guide | [docs/cli-guide.md](docs/cli-guide.md) |
| Onboarding | [docs/onboarding.md](docs/onboarding.md) |
| Integrations | [docs/integrations.md](docs/integrations.md) |
| Server setup | [docs/server-setup.md](docs/server-setup.md) |
| Upgrading | [docs/upgrading.md](docs/upgrading.md) |
| Roadmap | [ROADMAP.md](ROADMAP.md) |
