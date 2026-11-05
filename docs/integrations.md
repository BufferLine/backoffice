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
    │   ├── AirwallexProvider
    │   └── AspireProvider
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
| Aspire     |     ✓     |      ✓       |    -    |      -       |    -     |       -        |      -       |

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
│   ├── airwallex.py         # Airwallex provider
│   └── aspire.py            # Aspire provider (read-only)

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
- Default intervals: Airwallex txns 30min, balance 15min; Aspire txns 30min, balance 15min; Wise txns 2hr, balance 1hr
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

## Aspire

Read-only sync for the Aspire business account (transactions + balances).
API reference: https://docs.api.aspireapp.com/api (OpenAPI spec: `/api/v1.yaml`).

### Auth
- `POST /public/v1/login` with `{"grant_type": "client_credentials", "client_id", "client_secret"}`
- Returns `access_token` + `expires_in` (900s); cached in memory, refreshed 60s before expiry and on 401
- Create the API key in the Aspire web app (API menu). The client secret is shown only once.

### Transaction Sync
- `GET /public/v1/transactions?start_date=YYYY-MM-DDTHH:mm:ssZ&page=N` (page-based, `metadata.next_page_url`)
- `start_date` is required: first sync looks back `ASPIRE_SYNC_LOOKBACK_DAYS` (default 365); later syncs
  start 7 days before the last sync so late-settling rows are picked up (duplicates are dropped by
  the `(source, source_tx_id)` constraint)
- Amounts are integers in minor units (`135000` = SGD 1,350.00; IDR/JPY have none); debits are negative
- `tx_date` is the Singapore local date of the UTC `datetime`
- `pending` card transactions are skipped until they post/settle
- Only rows from active `debit` accounts are imported; credit-line (`advance`) rows are dropped even
  though they share the SGD currency (account IDs from `GET /accounts`, cached 10 min)
- If the first-ever backfill fails mid-way, the next run restarts from page 1 (the lookback window
  moves between runs, so a saved page number would point at different rows)
- Known limit: a row whose status changes later (e.g. `settled` → `refunded`) keeps its first snapshot
- Maps to `BankTransaction` with `source="aspire"`, `source_tx_id=id`, `reference=reference`,
  `counterparty=counterparty_name`, `description=ref_code` (the transaction ID shown in the Aspire app)

### Balance Sync
- `GET /public/v1/accounts` → active `debit` accounts only (credit-line `advance` accounts are ignored)
- Aspire may hold several accounts per currency (e.g. USD via DBS SWIFT and via Currency Cloud);
  balances are summed per currency, matching how transactions are merged into one ledger account
- Maps each currency to `Account.metadata_json.live_balance` for accounts with `statement_source="aspire"`

### Setup
```bash
acct account create --name "Aspire SGD" --type bank --currency SGD --institution Aspire \
  --opening-balance-date 2026-10-01
acct account update <account-id> --statement-source aspire   # link the account to the provider
acct integration test aspire
acct integration sync aspire
```

### Env Vars
```
ASPIRE_CLIENT_ID=xxx
ASPIRE_API_KEY=xxx
ASPIRE_BASE_URL=https://api.aspireapp.com/public/v1
ASPIRE_SYNC_LOOKBACK_DAYS=365
ENABLE_SYNC_SCHEDULER=true
```

Rate limit: < 100 requests/min per GET endpoint (429 on breach).

## On-chain Receipt Verification

`acct payment receive-crypto` verifies each stablecoin receipt against the chain before
recording it (`backend/app/services/onchain.py`), using plain JSON-RPC — no API key.

- Calls: `eth_chainId` (guards against a mis-pointed RPC), `eth_getTransactionReceipt`,
  `eth_blockNumber`, `eth_getBlockByNumber` (block time → default receipt date in SGT).
- Accepts only ERC-20 `Transfer` logs from the canonical contracts: Ethereum USDC/USDT, Base USDC.
- Recipient is the wallet account's `wallet_address`; the amount must match exactly; outbound
  transfers from that wallet in the same tx fail verification.
- Finality: block ≤ `safe` head and receipt block hash == canonical block hash; plus N confirmations.
- Rejects transfers that predate the invoice or come from our own wallets.
- Result (or skip reason) stored in `payments.onchain_verification`; skips are audited.
- Permissions: `payment:manage_wallets` to set/change wallet addresses (audited; locked once
  used by a verified receipt), `payment:skip_verification` to skip. Both: admin and superadmin only.
- tx hashes are unique case-insensitively (`uq_payments_tx_hash_lower`).
- RPC errors never echo the full URL (only the host), so keyed provider URLs are safe to configure.

```
ONCHAIN_RPC_ETHEREUM=https://ethereum-rpc.publicnode.com   # default; any provider URL works
ONCHAIN_RPC_BASE=https://mainnet.base.org                  # default
ONCHAIN_MIN_CONFIRMATIONS_ETHEREUM=12
ONCHAIN_MIN_CONFIRMATIONS_BASE=30
```

Read-only check: `acct payment verify-tx --chain base --tx-hash 0x... --account <wallet-account-id>`.

## DBS Statement Parser

Parser for DBS/POSB iBanking PDF statements.

### Capabilities

- Multi-currency accounts (SGD, USD, GBP, EUR, JPY, AUD, HKD)
- Multi-page consolidated statements
- Automatic counterparty and reference extraction
- Deterministic transaction IDs for deduplication

### Requirements

- `pdftotext` (from poppler-utils) must be installed on the host:
  ```bash
  # macOS
  brew install poppler

  # Ubuntu/Debian
  apt-get install poppler-utils
  ```

### Usage

```bash
acct bank import \
  --file statement.pdf \
  --source dbs \
  --account <account-id>
```

The parser uses `pdftotext -layout` to preserve table structure from PDF statements. Multi-currency accounts are automatically split by currency section.
