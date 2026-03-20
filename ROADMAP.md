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

## Up Next

### Agent Integration
- [ ] Agent reads todo list and executes tasks in order
- [ ] Task completion records execution result as note
- [ ] Agent escalates tasks it cannot handle to human

### Invoice
- [ ] Client attention/contact person field
- [ ] Custom notes/terms section per invoice
- [ ] Credit note support

### Payroll
- [ ] CPF rate table in DB (by age band, no code changes needed)
- [ ] SDL/CPF rate updates without code deployment
- [ ] Multi-jurisdiction payroll module (e.g. Korea)

### Payment Methods
- [ ] PayNow QR end-to-end test
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
