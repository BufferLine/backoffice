# Integration Framework Design

## Overview

Modular integration architecture where each external service is a **provider plugin** implementing capability-based interfaces. The framework handles auth, webhooks, background sync, and credential management.

## Architecture

```
API Layer
    │
    ├── POST /api/webhooks/{provider}     ← Incoming webhooks
    ├── GET/POST /api/integrations/*      ← Management endpoints
    │
    ▼
Integration Service (orchestration)
    │
    ├── Provider Registry
    │   └── AirwallexProvider  (only implemented provider)
    │
    ├── Webhook Service (verify → dedup → process)
    ├── Sync Scheduler (APScheduler, in-process)
    │
    ▼
Existing Services (unchanged)
    ├── bank_reconciliation → BankTransaction
    ├── payment → Payment + invoice state transition
    └── audit → AuditLog
```

## Capability Matrix

### Implemented

| Provider   | sync_txns | sync_balance | webhook | payment_link | transfer | verify_payment | push_invoice |
|------------|:---------:|:------------:|:-------:|:------------:|:--------:|:--------------:|:------------:|
| Airwallex  |     ✓     |      ✓       |    ✓    |      -       |    ✓     |       -        |      -       |

### Planned (not yet implemented)

| Provider   | sync_txns | sync_balance | webhook | payment_link | transfer | verify_payment | push_invoice |
|------------|:---------:|:------------:|:-------:|:------------:|:--------:|:--------------:|:------------:|
| Stripe     |     -     |      -       |    ✓    |      ✓       |    -     |       -        |      -       |
| Wise       |     ✓     |      ✓       |    -    |      -       |    ✓     |       -        |      -       |
| Etherscan  |     -     |      -       |    -    |      -       |    -     |       ✓        |      -       |
| Xero       |     -     |      -       |    ✓    |      -       |    -     |       -        |      ✓       |

## File Structure

```
backend/app/integrations/
├── __init__.py              # Registry: register_provider(), get_provider()
├── base.py                  # Provider ABC + capability mixins
├── capabilities.py          # Capability enum + data classes
├── exceptions.py            # ProviderAPIError, RateLimitError, WebhookSignatureError
├── providers/
│   ├── __init__.py          # Imports all providers to trigger registration
│   └── airwallex.py         # Implemented provider

backend/app/models/integration.py     # IntegrationEvent, SyncState, Config
backend/app/services/integration.py   # Sync orchestration
backend/app/services/webhook.py       # Webhook processing
backend/app/api/integrations.py       # Endpoints
backend/app/schemas/integration.py    # Pydantic schemas
backend/app/scheduler.py              # APScheduler setup
```

## DB Models

### integration_events
Webhook/sync event log with idempotency.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| provider | VARCHAR(50) | "airwallex", "stripe" |
| direction | VARCHAR(10) | "inbound" (webhook) / "outbound" (sync) |
| event_type | VARCHAR(100) | e.g. "financial_transaction.created" |
| provider_event_id | VARCHAR(255) | UNIQUE with provider — idempotency |
| payload_json | JSONB | |
| result_json | JSONB | |
| status | VARCHAR(20) | processing/processed/failed/rejected/duplicate |
| error_message | TEXT | |
| created_at | TIMESTAMPTZ | |

### integration_sync_states
Tracks sync progress per provider per account.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| provider | VARCHAR(50) | |
| capability | VARCHAR(50) | "sync_transactions", "sync_balance" |
| account_id | UUID FK | Nullable |
| last_synced_at | TIMESTAMPTZ | |
| last_cursor | VARCHAR(500) | Pagination cursor |
| consecutive_failures | INTEGER | Auto-skip after 5 |
| last_error | TEXT | |

### integration_configs
Runtime config (OAuth tokens, tenant IDs).

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| provider | VARCHAR(50) | |
| config_key | VARCHAR(100) | UNIQUE with provider |
| config_value | TEXT | Encrypted at rest |
| expires_at | TIMESTAMPTZ | For token expiry |

## Data Flows

### Transaction Sync (Polling)
```
Scheduler → provider.sync_transactions(since, cursor)
  → list[SyncedTransaction]
  → INSERT bank_transactions (source=provider, source_tx_id=...)
  → ON CONFLICT DO NOTHING (existing UniqueConstraint)
  → UPDATE sync_state (cursor, last_synced_at)
```

### Webhook → Invoice Paid (Stripe example)
```
POST /api/webhooks/stripe
  → verify_webhook_signature (Stripe-Signature header)
  → parse_webhook → WebhookEvent(payment_intent.succeeded)
  → check integration_events for event_id (dedup)
  → handle_event → extract invoice_id from metadata
  → payment_service.record_payment(idempotency_key=stripe:{event_id})
  → payment_service.link_payment → invoice_machine.transition(issued → paid)
```

### Balance Sync
```
Scheduler → provider.sync_balances()
  → list[BalanceInfo]
  → UPDATE account.metadata_json.live_balance
```

## Webhook System

- Single endpoint: `POST /api/webhooks/{provider}`
- No auth required (verified via provider-specific signatures)
- Always returns 200 (prevent provider retries on our errors)
- Idempotency via `(provider, provider_event_id)` unique constraint
- Event logged before processing (record exists even if processing fails)

## Background Sync

- APScheduler AsyncIOScheduler (same event loop as FastAPI)
- Configurable per provider: `ENABLE_SYNC_SCHEDULER=true`
- Default intervals: Airwallex txns 30min, balance 15min; Wise txns 2hr, balance 1hr
- Rate limit errors tracked; auto-skip after 5 consecutive failures

## Credentials

- **Static** (env vars): API keys, webhook secrets — `AIRWALLEX_CLIENT_ID`, `STRIPE_SECRET_KEY`
- **Dynamic** (DB): OAuth2 tokens, cursors — `integration_configs` table
- Never logged, never in API responses

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | /api/webhooks/{provider} | Signature | Webhook receiver |
| GET | /api/integrations | integration:read | List providers + status |
| GET | /api/integrations/{provider} | integration:read | Provider detail |
| POST | /api/integrations/{provider}/test | integration:write | Test connection |
| POST | /api/integrations/{provider}/sync | integration:write | Trigger manual sync |
| GET | /api/integrations/{provider}/events | integration:read | Event log |

## CLI Commands

```bash
acct integration list                        # Show configured providers
acct integration test airwallex              # Test connection
acct integration sync airwallex              # Manual sync
acct integration events airwallex --limit 20 # View events
```

## Airwallex — First Provider

### Auth
- `POST /api/v1/authentication/login` with `x-client-id` + `x-api-key`
- Returns bearer token (30min expiry, cached in memory)

### Transaction Sync
- `GET /api/v1/financial_transactions` (paginated, date-filtered)
- Maps to `BankTransaction` with `source="airwallex"`

### Balance Sync
- `GET /api/v1/balances/current`
- Maps each currency wallet to `Account.metadata_json.live_balance`

### Webhooks
| Event | Action |
|-------|--------|
| `financial_transaction.created` | Create BankTransaction → auto-match |
| `payment_attempt.settled` | Update payment status |
| `payout.completed` | Mark transfer as completed |
| `payout.failed` | Mark transfer failed + create follow-up task |

### Env Vars
```
AIRWALLEX_CLIENT_ID=xxx
AIRWALLEX_API_KEY=xxx
AIRWALLEX_BASE_URL=https://api.airwallex.com
AIRWALLEX_WEBHOOK_SECRET=xxx
ENABLE_SYNC_SCHEDULER=true
```
