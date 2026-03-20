# Backoffice

Backoffice operations system for small companies. Invoice, payroll, expense, payment tracking with month-end accountant handoff.

Built for Singapore compliance (SDL, CPF, GST) with modular jurisdiction support.

## Features

- **Invoices** — draft, issue, PDF generation with stamp, PayNow QR, GST breakdown
- **Payroll** — prorated salary, SDL/CPF calculation, payslip PDF
- **Expenses** — categorize, attach receipts, track reimbursements
- **Payments** — bank transfer and crypto, FX tracking, link to invoices/payroll
- **Bank reconciliation** — import CSV statements (Airwallex, DBS, OCBC), auto-match
- **Accounts** — track balances across bank, crypto, and cash accounts
- **Exports** — monthly ZIP pack (CSVs + PDFs + manifest) for accountant handoff
- **Compliance calendar** — Singapore SDL, CPF, GST, IR8A deadlines as tasks
- **Audit log** — full history with field-level change tracking

## Quick Start

```bash
# 1. Clone and enter
git clone https://github.com/YOUR_ORG/backoffice.git && cd backoffice

# 2. Full reset — starts Docker, creates DB, runs migrations, starts server
scripts/reset.sh

# 3. Initialize your company
acct init --company-name "Your Company Pte Ltd" --jurisdiction SG

# 4. Open the printed URL in browser to create your admin account, then login
acct login --email you@company.com
```

## Documentation

| Doc | Description |
|-----|-------------|
| [Onboarding](docs/onboarding.md) | First-time setup walkthrough |
| [CLI Guide](docs/cli-guide.md) | Full command reference |
| [Server Setup](docs/server-setup.md) | Production deployment guide |
| [Development](docs/development.md) | Local dev environment |
| [Architecture](docs/architecture.md) | System design and data model |

## Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2.0 (async), PostgreSQL 16
- **CLI**: Typer + httpx + Rich
- **PDF**: Jinja2 + WeasyPrint
- **Storage**: MinIO (S3-compatible) / Cloudflare R2 in production
- **Frontend**: Next.js 15, TypeScript, Tailwind CSS
- **Infra**: Docker Compose (dev) / Cloudflare Tunnel (production)

## License

MIT
