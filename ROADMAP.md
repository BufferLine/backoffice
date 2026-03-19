# Backoffice Roadmap

## Completed

- [x] Todo auto-generation: payroll finalize, invoice issue, overdue follow-up
- [x] Todo list/upcoming auto-generates instances for current month
- [x] Export validate CLI 405 fix
- [x] Multi payment method per invoice (join table)
- [x] Per-line-item tax code (SR/ZR/ES/NT) with rate override
- [x] GST breakdown by rate in invoice PDF
- [x] GST Registration Number + Website in company settings
- [x] PayNow QR code generation on invoice PDF
- [x] Fix empty 2nd page on PDF (footer/stamp overflow)
- [x] File download API (GET /api/files/{id}/download)
- [x] Company logo on payslip

## Todo System (Agent Task Queue)

### Agent Integration
- [ ] Agent가 todo list 조회 → 실행 가능한 task 순서대로 처리
- [ ] Task complete 시 실행 결과 note로 기록
- [ ] Agent가 처리 못하는 task는 사람에게 알림

## Invoice

### Template Polish
- [ ] Client attention/contact person field
- [ ] Invoice notes/terms section (custom per invoice)
- [ ] Credit note support

## Payroll

- [ ] CPF rate table DB화 (age band별)
- [ ] SDL/CPF rate 변경 시 코드 수정 불필요하게
- [ ] Multi-jurisdiction payroll module (KR 등)

## Payment Methods

- [ ] PayNow QR end-to-end test
- [ ] Payment method validation (bank requires bank fields, crypto requires wallet)

## Accounts / Balance

- [ ] Dashboard: monthly cashflow chart (in/out by category)
- [ ] Auto-create transaction when payment is linked
- [ ] Recurring commitment → pending transaction auto-match with bank import

## Frontend

- [ ] Settings: payment method CRUD UI
- [ ] Settings: company branding preview (logo, stamp, colors)
- [ ] Invoice: multi payment method selector on create/edit
- [ ] Invoice: PDF preview before issuing
- [ ] Dashboard: KPI cards with real data
- [ ] Payroll: create/review/finalize flow

## Infrastructure

- [ ] Docker: full stack docker-compose up (backend + frontend)
- [ ] CI/CD: GitHub Actions for test + lint
- [ ] Production deployment config
