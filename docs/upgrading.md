# Upgrading

## v0.2.0 — Payment Allocations & Loans

**Breaking changes**: None. Fully backward compatible.

### What changed

- **New table: `loans`** — Track shareholder loans, director loans, bank loans with principal, interest rate, maturity, and repayment status.
- **New table: `payment_allocations`** — Many-to-many relationship between payments and documents (invoices, expenses, loans, payroll). Enables partial payments, split payments, and loan repayment tracking.
- **New API endpoints**: 7 loan endpoints (`/api/loans/*`), 3 allocation endpoints (`/api/payments/*/allocate`, `/api/payments/*/allocations`, `/api/payments/allocations/*`).
- **New permissions**: `loan:read`, `loan:write` — automatically seeded on server startup.

### How payments work now

Previously, each `Payment` was linked to exactly one document via `related_entity_type` + `related_entity_id` (1:1). This still works and is unchanged.

The new `PaymentAllocation` table adds many-to-many support:

```
Payment $10,000 (from client)
  ├─ Allocation → Invoice A: $6,000
  └─ Allocation → Invoice B: $4,000

Loan $60,000 (shareholder loan)
  ├─ Allocation → Drawdown payment: $60,000
  ├─ Allocation → Repayment month 1: $5,000
  └─ Allocation → Repayment month 2: $5,000
  Outstanding = $50,000
```

### Upgrade steps

#### 1. Back up your database

```bash
pg_dump -h localhost -U backoffice backoffice > backup_before_v020.sql
```

#### 2. Pull the latest code

```bash
git pull origin main
```

#### 3. Install new dependencies

```bash
cd backend
source .venv/bin/activate
pip install -e "."
```

No new Python packages are required for this release.

#### 4. Run the migration

```bash
cd backend
source .venv/bin/activate
alembic upgrade head
```

This migration:
1. Creates the `loans` table
2. Creates the `payment_allocations` table with indexes
3. **Automatically migrates existing payment data**: All payments with `related_entity_type` and `related_entity_id` are copied into `payment_allocations` so outstanding balance calculations work immediately

#### 5. Restart the server

```bash
# Development
scripts/dev.sh

# Production (Docker)
docker compose restart backend
```

On startup, the new `loan:read` and `loan:write` permissions are automatically seeded.

#### 6. Verify

```bash
# Check migration applied
curl http://localhost:8000/health

# Check loans endpoint is available
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/loans
# Should return: {"items": [], "total": 0}

# Check existing payment allocations migrated
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/payments/$PAYMENT_ID/allocations
# Should return existing payment linkages as allocations
```

### Deprecation notice

`Payment.related_entity_type` and `Payment.related_entity_id` are **soft-deprecated**. They continue to work but new code should use `PaymentAllocation` for linking payments to documents. These fields will be removed in a future version.

### Rollback

If you need to roll back:

```bash
cd backend
alembic downgrade a1b2c3d4e5f6
```

This drops the `payment_allocations` and `loans` tables. Existing payment data (in `related_entity_type/id`) is unaffected.
