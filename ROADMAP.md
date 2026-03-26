# Roadmap

## Completed

- [x] Invoice CRUD + PDF generation with company stamp/logo/branding
- [x] Payroll with proration, SDL/CPF, payslip PDF
- [x] Expense tracking with state machine (draft → confirmed → reimbursed)
- [x] Payment recording (bank + crypto) with invoice/payroll linking
- [x] Bank statement import + auto-match reconciliation
- [x] Account balance tracking (accounts + transactions ledger)
- [x] Recurring commitments (subscriptions, rent)
- [x] Month-end export pack (ZIP with CSVs + PDFs + manifest)
- [x] Todo/task system with Singapore compliance calendar (10 templates)
- [x] Todo auto-generation on business events (invoice issue, payroll finalize, overdue)
- [x] Field-level change log tracking
- [x] Multi payment method per invoice
- [x] Per-line-item tax code (SR/ZR/ES/NT) with rate override
- [x] PayNow QR code generation on invoice PDF
- [x] Payment methods registry (bank/crypto/PayNow) with nickname
- [x] GST inclusive/exclusive pricing
- [x] Company branding (logo, stamp, color theme, font)
- [x] File download API + CLI
- [x] Payroll delete/edit/regenerate PDF
- [x] Onboarding flow (CLI + browser, or CLI-only with --admin-email)
- [x] JWT + API token auth with domain-based RBAC
- [x] Docker Compose production (backend + frontend + nginx + cloudflared)
- [x] Supabase DB + Cloudflare R2 storage support
- [x] Comprehensive documentation (onboarding, CLI guide, server setup, architecture)

---

## Integrations

Modular integration architecture: each provider is a plugin with API client, webhook handler, and sync logic. Credentials stored via env vars per provider.

### Phase 1 — Quick Wins (Low effort, high value)

#### PayNow SGQR Fix
- [x] Replace URL-based QR with proper EMVCo/SGQR TLV format
- [x] Test with DBS, OCBC, UOB mobile banking apps
- [x] Add amount + reference encoding per SGQR spec

#### DBS Statement Parser
- [x] Add `DBSParser` for DBS iBanking PDF statement format
- [ ] Handle IDEAL (corporate) CSV variant
- [x] Register in statement_parsers registry

#### Crypto On-chain Verification
- [ ] Verify `tx_hash` via Etherscan/Polygonscan API after payment recording
- [ ] Check: transaction exists, amount matches, destination matches, N confirmations
- [ ] Store verification status on payment record
- [ ] Support multiple chains via `chain_id` field (Ethereum, Polygon, Arbitrum)

### Phase 2 — Bank API Sync (Medium effort, high value)

#### Integration Infrastructure
- [x] Background task scheduler (APScheduler) for periodic API polling
- [x] Webhook receiver framework with signature verification per provider
- [ ] Rate limiter for outbound API calls (per-provider limits)
- [x] `integration_credentials` config pattern (env vars grouped by provider)

#### Airwallex API
- [x] API client module (`AIRWALLEX_CLIENT_ID`, `AIRWALLEX_API_KEY` env vars)
- [x] Token auth flow (short-lived bearer token from client_id + api_key)
- [x] Transaction history sync → `BankTransaction` records (replaces CSV import)
- [x] Real-time balance sync → `Account.balance` verification
- [x] Webhook receiver: `payment.completed`, `payout.completed` → auto-create transactions
- [x] FX rate fetching for `fx_rate_to_sgd` on payments
- [x] Payment link generation for international invoice clients

#### Stripe Payment Collection
- [ ] Stripe Payment Link generation on invoice issue
- [ ] Embed payment link/button in invoice PDF
- [ ] Webhook: `payment_intent.succeeded` → auto-mark invoice as paid
- [ ] Handle partial payments and refunds
- [ ] Store Stripe payment ID on our payment record

### Phase 3 — Extended Banking (Medium-High effort)

#### Wise Integration
- [ ] API client (personal API token auth)
- [ ] Multi-currency balance sync → `Account` records
- [ ] Transaction history API → `BankTransaction` records
- [ ] Batch payment for payroll (create quote → recipient → transfer → fund)
- [ ] Handle SCA (Strong Customer Authentication) approval flow
- [ ] Webhook: `transfers#state-change`, `balances#credit`

#### Accounting Software Sync
- [ ] Xero OAuth2 client (token management, browser auth, auto-refresh)
- [ ] Push invoices to Xero on issue
- [ ] Push payments to Xero on recording
- [ ] Push expenses to Xero on confirmation
- [ ] Map per-line-item tax codes (SR/ZR/ES/NT) to Xero tax rates
- [ ] QuickBooks Online as alternative (same architecture, different mapping)

### Phase 4 — Advanced (High effort, conditional)

#### DBS RAPID API
- [ ] mTLS + OAuth2 client credentials (requires DBS corporate relationship)
- [ ] Real-time balance and transaction notifications
- [ ] Payment initiation (FAST/GIRO/PayNow)
- [ ] Only viable for companies qualifying for RAPID access

#### Multi-chain Crypto
- [ ] Auto-detect incoming stablecoin payments via address monitoring
- [ ] Alchemy Notify / QuickNode Streams webhooks for wallet activity
- [ ] Support: Ethereum, Polygon, Arbitrum, Base (configurable per account)
- [ ] Auto-create `BankTransaction` on detected incoming transfer

---

## Up Next

### Agent Integration
- [ ] Agent reads todo list and executes tasks in order
- [ ] Task completion records execution result as note
- [ ] Agent escalates tasks it cannot handle to human

### Invoice
- [ ] Customizable invoice number format (prefix, padding, reset period)
- [ ] Client attention/contact person field
- [ ] Custom notes/terms section per invoice
- [ ] Credit note support

### Payroll
- [ ] Customizable payslip number format (prefix, padding, reset period)
- [ ] CPF rate table in DB (by age band, no code changes needed)
- [ ] SDL/CPF rate updates without code deployment
- [ ] Multi-jurisdiction payroll module (e.g. Korea)

### Shareholder Loan
- [x] Director/shareholder loan ledger (drawdown, repayment, interest)
- [x] Loan agreement PDF generation (terms, schedule, signatures)
- [x] Interest calculation (simple/compound, configurable rate)
- [ ] Repayment schedule tracking with reminders
- [ ] Loan document lifecycle: Agreement (immutable) / Statement (regeneratable) / Discharge Letter (on completion)
- [ ] DocuSign integration for e-signatures (via SignatureProvider mixin)

### Task / Todo
- [ ] User-level task assignment (assign tasks to specific users, filter by assignee)
- [ ] Task dashboard with workload view per user

### Payment Methods
- [ ] Validation: bank type requires bank fields, crypto requires wallet

### Double-Entry Bookkeeping
- [x] JournalEntry + JournalLine models (debit/credit with balance constraint)
- [x] Account classification (asset/liability/equity/revenue/expense)
- [x] Journal service: CRUD, confirm, trial balance, account ledger
- [x] Reconciliation → JournalEntry auto-creation
- [x] Account balance from journal lines (debit-normal / credit-normal)
- [x] API: /api/journal-entries, /api/journal-entries/trial-balance, reconcile endpoint
- [x] CLI: acct journal, acct report trial-balance, acct bank tx-reconcile
- [x] Fix float → Decimal in payment SGD calculation
- [ ] Agent-assisted categorization (auto-classify bank transactions)
- [ ] Income statement (P&L) report
- [ ] Balance sheet report
- [ ] Deprecate old Transaction table after full transition

### Accounts & Balance
- [ ] Monthly cashflow chart (inflow/outflow by category)
- [ ] Recurring commitment → pending transaction auto-match with bank import

### Frontend
- [ ] Payment method CRUD UI
- [ ] Company branding preview (logo, stamp, colors)
- [ ] Invoice: multi payment method selector
- [ ] Invoice: PDF preview before issuing
- [ ] Dashboard: KPI cards with live data
- [ ] Payroll: create/review/finalize flow

### Agent / Plugin
- [ ] `acct setup-skill --platform claude|codex|gemini` for AI tool integration
- [ ] Research platform-specific skill/plugin standards as they mature
- [ ] Multi-step workflow agent mode (natural language → CLI execution)
- [ ] Agent remote memory system (per-agent, per-user persistent context)
  <!-- Defer until multi-user/multi-agent is actually needed.
       - Currently single-user; no real demand for memory isolation yet.
       - Scope unclear: simple key-value vs vector search vs session-based.
       - AI platforms (Claude, Codex, Gemini) already ship their own memory.
       - Prioritize business-value items (DBS parser, Stripe, crypto verification) first. -->

### Notion Integration
- [ ] Use Notion as document/data store (tasks, notes, meeting logs)
- [ ] Sync task instances ↔ Notion database
- [ ] Store generated PDFs and attachments in Notion pages

### Auth / CLI
- [ ] E2E tests for API token lifecycle (create-token → login --token → whoami → revoke-token)

### Security
- [ ] Fix bootstrap race condition: concurrent `/api/setup/init` can mint multiple superadmins
- [ ] Re-check DB permissions on each request instead of trusting JWT-embedded permissions
- [ ] Encrypt integration secrets at rest (currently plaintext in `integration_configs`)
- [ ] File upload: validate content via magic bytes, enforce size limit before reading into memory

### Code Quality
- [ ] Add Ruff + mypy to backend/CLI (frontend already has ESLint)
- [ ] Replace broad `except Exception: pass` with narrow catches + logging (invoice, payroll, api_client)
- [ ] Refactor `frontend/src/app/settings/page.tsx` — extract static data and split components
- [ ] Fix frontend `api.ts` empty-response handling (crashes on 200 with empty body)

### Test Coverage
- [ ] Endpoint tests: users, setup, bank_reconciliation, exports, loans, payment_methods, files, automation
- [ ] Service unit tests: payment_allocation, invoice, transaction, integration, automation
- [ ] Fill partial gaps: auth (logout/token delete), invoices (line-item/PDF), payroll (PDF/delete), expenses (reimburse)
- [ ] Automate test DB provisioning (testcontainers or docker-compose preflight)

### Infrastructure
- [x] CI/CD: GitHub Actions for test + lint
- [ ] Automated backup strategy
- [ ] Health check monitoring + alerts
