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
- [ ] Add `DBSParser` for DBS iBanking CSV format
- [ ] Handle both iBanking and IDEAL (corporate) CSV variants
- [ ] Register in statement_parsers registry

#### Crypto On-chain Verification
- [ ] Verify `tx_hash` via Etherscan/Polygonscan API after payment recording
- [ ] Check: transaction exists, amount matches, destination matches, N confirmations
- [ ] Store verification status on payment record
- [ ] Support multiple chains via `chain_id` field (Ethereum, Polygon, Arbitrum)

### Phase 2 — Bank API Sync (Medium effort, high value)

#### Integration Infrastructure
- [ ] Background task scheduler (APScheduler or Celery) for periodic API polling
- [ ] Webhook receiver framework with signature verification per provider
- [ ] Rate limiter for outbound API calls (per-provider limits)
- [ ] `integration_credentials` config pattern (env vars grouped by provider)

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
- [ ] Director/shareholder loan ledger (drawdown, repayment, interest)
- [ ] Loan agreement PDF generation (terms, schedule, signatures)
- [ ] Interest calculation (simple/compound, configurable rate)
- [ ] Repayment schedule tracking with reminders

### Payment Methods
- [ ] Validation: bank type requires bank fields, crypto requires wallet

### Accounts & Balance
- [ ] Monthly cashflow chart (inflow/outflow by category)
- [ ] Auto-create transaction when payment is linked
- [ ] Recurring commitment → pending transaction auto-match with bank import

### Frontend
- [ ] Payment method CRUD UI
- [ ] Company branding preview (logo, stamp, colors)
- [ ] Invoice: multi payment method selector
- [ ] Invoice: PDF preview before issuing
- [ ] Dashboard: KPI cards with live data
- [ ] Payroll: create/review/finalize flow

### Infrastructure
- [ ] CI/CD: GitHub Actions for test + lint
- [ ] Automated backup strategy
- [ ] Health check monitoring + alerts
