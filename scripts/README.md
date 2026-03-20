# Scripts

## Development

| Script | Description |
|--------|-------------|
| `reset.sh` | Full reset: stops services, wipes DB, runs migrations, starts server |
| `dev.sh` | Start dev server (preserves existing data) |
| `stop.sh` | Stop all services (uvicorn + Docker) |
| `test.sh` | Run pytest against test database |
| `e2e.sh` | API-level E2E test (31 checks via curl) |
| `e2e-cli.sh` | CLI-level E2E test (36 checks via `acct` commands) |
| `seed-demo.sh` | Seed demo data (clients, invoices, employees, expenses) |

## Production

| Script | Description |
|--------|-------------|
| `setup-production.sh` | One-time server setup (venv, deps, CLI, migrations, service) |
| `install-service.sh` | Generate and install macOS launchd service plist |
| `update.sh` | Pull latest code, install deps, run migrations, restart service |

## Environment Variables

E2E scripts support these overrides:

| Variable | Default | Description |
|----------|---------|-------------|
| `TEST_EMAIL` | `admin@test.local` | Admin email for test runs |
| `TEST_PASSWORD` | `TestPass123!` | Admin password for test runs |
| `TEST_COMPANY` | `Test Company Pte Ltd` | Company name for test runs |
| `TEST_UEN` | `000000000X` | UEN for test runs |
| `TEST_EMPLOYEE` | `Test Employee` | Employee name for test runs |
