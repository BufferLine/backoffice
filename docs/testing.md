# Testing

## Quick Reference

```bash
scripts/ci.sh              # Full CI: unit + reset + API E2E + reset + CLI E2E
python -m pytest backend/tests/unit/ -v   # Unit tests only (no server needed)
scripts/e2e.sh             # API E2E only (server must be running, fresh DB)
scripts/e2e-cli.sh         # CLI E2E only (server must be running, fresh DB)
```

## Test Tiers

### Tier 1: Unit Tests (334 tests, ~0.2s)

Pure logic tests with no database or server dependency.

**Location**: `backend/tests/unit/`

| File | Tests | Coverage |
|------|-------|----------|
| `test_state_machines.py` | 87 | Invoice/payroll/expense state transitions |
| `test_jurisdiction.py` | 72 | SG CPF/SDL/GST/proration calculations |
| `test_parsers.py` | 55 | Airwallex/Generic CSV parsing |
| `test_schemas.py` | 89 | Pydantic validation, safe_filename, PDF helpers |
| `test_paynow_qr.py` | 20 | SGQR EMVCo TLV payload generation |
| `test_airwallex.py` | 11 | Airwallex provider capabilities + FX/payment link |

**Run**: `python -m pytest backend/tests/unit/ -v`

**When to run**: Always — before every commit.

### Tier 2: API E2E (40 tests, ~10s)

HTTP-level tests against a running server. Covers full business workflows via REST API.

**Run**: `scripts/e2e.sh` (requires fresh reset)

**When to run**: Before opening a PR.

### Tier 3: CLI E2E (38 tests, ~15s)

End-to-end tests through the `acct` CLI tool. Covers the full workflow from onboarding to month-end.

**Run**: `scripts/e2e-cli.sh` (requires fresh reset)

**When to run**: Before opening a PR, if CLI or API changes are involved.

## CI Pipeline (`scripts/ci.sh`)

Runs all three tiers sequentially with automatic resets between E2E phases:

```
Phase 1: Unit Tests         (no server)
Phase 2: Reset → API E2E    (fresh DB)
Phase 3: Reset → CLI E2E    (fresh DB)
```

**When to run**: Before opening a PR. Required to pass for merge.

## Pre-PR Checklist

Before opening a PR, ensure:

1. `python -m pytest backend/tests/unit/ -v` — all pass
2. If you changed backend code: `scripts/ci.sh` — all pass
3. If you added new logic: add unit tests in `backend/tests/unit/`
4. If you changed API endpoints: verify `scripts/e2e.sh` passes
5. If you changed CLI commands: verify `scripts/e2e-cli.sh` passes

## Writing Unit Tests

### Location & Naming

- All unit tests go in `backend/tests/unit/`
- File naming: `test_{module}.py`
- The `conftest.py` in this dir overrides the DB fixture — no database needed

### Conventions

```python
# Class-based grouping
class TestInvoiceStateMachine:
    def test_draft_to_issued(self):
        ...

    def test_cannot_issue_cancelled(self):
        ...
```

- `test_{what_it_does}` — positive case
- `test_{what_fails}_when_{condition}` — negative case
- Use `Decimal` for money, never `float`
- Use `pytest.raises(ExceptionType)` and verify exception attributes
- For async: `@pytest.mark.asyncio` + `unittest.mock.AsyncMock`

### What to Unit Test

| Category | Examples |
|----------|---------|
| State machines | Valid/invalid transitions, available_actions |
| Jurisdiction | CPF/SDL/GST/proration calculations |
| Parsers | CSV parsing, edge cases, malformed input |
| Schemas | Pydantic validation, required/optional fields |
| Utilities | safe_filename, TLV encoding, CRC, formatters |

### What NOT to Unit Test

- Database queries → integration tests (`backend/tests/test_*.py`)
- API endpoints with DB → E2E tests
- External API calls → mock them

## Coverage

```bash
python -m pytest backend/tests/unit/ --cov=backend/app --cov-report=term-missing
```

Target: 100% on pure logic modules (state machines, jurisdiction, parsers, schemas).
