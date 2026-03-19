ckoffice Ops System Design Doc

## 1. Overview

이 시스템은 전통적인 회계 시스템을 대체하려는 것이 아니다. 목표는 **1인/소규모 법인의 backoffice operations를 자동화**하고, 최종 회계 및 세무 처리 전 단계의 **정합성 있는 운영 데이터와 증빙 패키지**를 생성하는 것이다.

핵심 범위는 다음과 같다.

* Invoice 생성, 발행, 상태 관리
* Payroll 계산, payslip 생성, 지급 증빙 관리
* Expense / Payment / Evidence 관리
* Month-end handoff package 생성
* Daily / Weekly / Monthly automation 실행
* Agent 기반 오케스트레이션 지원

최종 filing, tax treatment 확정, statutory submission은 accountant 또는 외부 회계 서비스가 담당한다.

---

## 2. Goals

### 2.1 Primary Goals

* Deterministic backend를 중심으로 정합성 있는 backoffice 운영 시스템 구축
* Agent는 실행 권한자가 아니라 orchestration layer로만 동작
* CLI를 중심으로 재현 가능한 운영 흐름 확보
* Frontend는 thin UI로 상태 조회 및 일부 승인/수정 기능 제공
* Accountant handoff를 위한 export-first 구조 확립

### 2.2 Non-Goals

* Full ERP 구축
* 법정 회계 분개 시스템 완전 대체
* 세무 신고 자동 제출
* agent가 회계 판단을 직접 수행하는 구조

---

## 3. Design Principles

### 3.1 Boring Core, Agentic UX

* 핵심 계산과 상태 변경은 backend API/CLI에서만 수행
* agent는 자연어 해석 및 tool invocation만 담당

### 3.2 Deterministic State Transitions

* invoice, payroll, export 등 주요 엔티티는 상태 머신 기반으로 관리
* 동일 입력에 대해 동일 출력 보장

### 3.3 Evidence First

* 모든 금전 흐름과 문서 생성 결과에는 증빙 첨부가 가능해야 함
* 숫자보다 증빙을 우선시

### 3.4 Export First

* accountant 전달용 CSV / PDF / ZIP 패키지 생성이 최우선
* UI보다 handoff 품질을 우선

### 3.5 Idempotent Operations

* issue, finalize, export 같은 명령은 중복 실행에도 안전해야 함

### 3.6 Auditability

* 누가, 언제, 어떤 입력으로, 어떤 상태를 만들었는지 추적 가능해야 함

---

## 4. High-Level Architecture

### 4.1 Components

1. **Backend API**

   * system of record
   * validation, state transition, document generation 담당

2. **CLI**

   * 운영자/agent가 사용하는 primary execution interface
   * batch 처리, 복구, automation entrypoint 역할

3. **Frontend**

   * thin dashboard
   * list / detail / approve / attach / export 중심

4. **Storage**

   * relational DB for metadata/state
   * object storage for documents/evidence

5. **Automation Runner**

   * scheduled jobs for daily / weekly / monthly routines

6. **Agent Skills Layer**

   * Claude Code / Codex가 호출하는 표준화된 skill set
   * 직접 DB 수정 금지, API/CLI만 사용

---

## 5. Core Domains

### 5.1 Invoices

기능 범위:

* draft 생성
* line item 관리
* invoice number 부여
* issue / cancel / mark paid
* PDF 생성
* recurring invoice 지원

핵심 상태:

* draft
* issued
* paid
* cancelled

### 5.2 Payroll

기능 범위:

* 월별 payroll run 생성
* prorated salary 계산
* SDL 계산
* payslip 생성
* 지급 기록 관리

핵심 상태:

* draft
* reviewed
* finalized
* paid

### 5.3 Expenses

기능 범위:

* 비용 기록
* category tagging
* 영수증 첨부
* reimbursable 여부 구분

### 5.4 Payments

기능 범위:

* fiat / crypto payment 기록
* invoice / payroll / expense와의 연결
* tx hash, bank reference, proof 저장
* fx metadata 저장

### 5.5 Documents / Evidence

기능 범위:

* invoice PDF
* payslip PDF
* receipt
* bank proof
* agreement copy
* month-end export ZIP

### 5.6 Exports / Handoff

기능 범위:

* 월별 accountant package 생성
* CSV + PDF + attachments manifest 포함
* immutable export snapshot 저장

---

## 6. Proposed Tech Stack

### 6.1 Preferred Stack

* Backend: Python + FastAPI
* CLI: Python + Typer
* DB: PostgreSQL
* ORM: SQLAlchemy or SQLModel
* File Storage: S3-compatible storage (or local fs for MVP)
* Frontend: Next.js
* PDF: HTML template + Playwright / WeasyPrint
* Scheduler: Cron or lightweight job runner

### 6.2 Why Python

* PDF / CSV / automation / scripting 친화적
* CLI와 backend를 같은 언어로 통일 가능
* Claude Code / Codex 기반 codegen에도 유리

---

## 7. Data Model (MVP)

### 7.1 clients

* id
* legal_name
* billing_email
* billing_address
* default_currency
* payment_terms_days
* preferred_payment_method
* metadata_json

### 7.2 invoices

* id
* invoice_number
* client_id
* issue_date
* due_date
* currency
* subtotal_amount
* tax_amount
* total_amount
* status
* description
* payment_method
* wallet_address
* issued_pdf_file_id
* created_at
* updated_at

### 7.3 invoice_line_items

* id
* invoice_id
* description
* quantity
* unit_price
* amount
* sort_order

### 7.4 payroll_runs

* id
* employee_name
* month
* start_date
* end_date
* monthly_base_salary
* prorated_gross_salary
* sdl_amount
* net_salary
* status
* payslip_file_id
* paid_at
* created_at
* updated_at

### 7.5 expenses

* id
* expense_date
* vendor
* category
* currency
* amount
* payment_method
* reimbursable
* notes
* created_at
* updated_at

### 7.6 payments

* id
* payment_type
* related_entity_type
* related_entity_id
* payment_date
* currency
* amount
* fx_rate_to_sgd
* sgd_value
* tx_hash
* bank_reference
* proof_file_id
* notes

### 7.7 files

* id
* storage_key
* original_filename
* mime_type
* size_bytes
* checksum_sha256
* uploaded_at
* linked_entity_type
* linked_entity_id

### 7.8 export_packs

* id
* month
* generated_at
* zip_file_id
* manifest_file_id
* status
* notes

### 7.9 audit_logs

* id
* actor_type
* actor_id
* action
* entity_type
* entity_id
* input_json
* output_json
* created_at

---

## 8. API Design (MVP)

### 8.1 Invoice APIs

* `POST /api/invoices`
* `GET /api/invoices`
* `GET /api/invoices/{id}`
* `POST /api/invoices/{id}/issue`
* `POST /api/invoices/{id}/mark-paid`
* `POST /api/invoices/{id}/cancel`
* `POST /api/invoices/{id}/attach-file`

### 8.2 Payroll APIs

* `POST /api/payroll/runs`
* `GET /api/payroll/runs`
* `GET /api/payroll/runs/{id}`
* `POST /api/payroll/runs/{id}/review`
* `POST /api/payroll/runs/{id}/finalize`
* `POST /api/payroll/runs/{id}/mark-paid`
* `POST /api/payroll/runs/{id}/attach-file`

### 8.3 Expense APIs

* `POST /api/expenses`
* `GET /api/expenses`
* `GET /api/expenses/{id}`
* `PATCH /api/expenses/{id}`
* `POST /api/expenses/{id}/attach-file`

### 8.4 Payment APIs

* `POST /api/payments`
* `GET /api/payments`
* `GET /api/payments/{id}`
* `POST /api/payments/reconcile`

### 8.5 Export APIs

* `POST /api/exports/month-end`
* `GET /api/exports`
* `GET /api/exports/{id}`

---

## 9. CLI Design (MVP)

### 9.1 Invoice Commands

* `acct invoice create`
* `acct invoice issue <invoice-id>`
* `acct invoice mark-paid <invoice-id>`
* `acct invoice attach-file <invoice-id> <path>`

### 9.2 Payroll Commands

* `acct payroll run --month 2026-03 --salary 9500 --start-date 2026-03-19`
* `acct payroll review <run-id>`
* `acct payroll finalize <run-id>`
* `acct payroll mark-paid <run-id> --proof <path>`

### 9.3 Expense Commands

* `acct expense add`
* `acct expense attach-file <expense-id> <path>`

### 9.4 Payment Commands

* `acct payment record`
* `acct payment reconcile`

### 9.5 Export Commands

* `acct export month-end --month 2026-03`

### 9.6 Automation Commands

* `acct automation daily`
* `acct automation weekly`
* `acct automation monthly --month 2026-03`

---

## 10. Frontend Scope

### 10.1 Dashboard

* outstanding invoices
* upcoming payroll
* recent expenses
* export pack history

### 10.2 Invoices UI

* list / filter / detail / PDF preview / mark paid

### 10.3 Payroll UI

* payroll run list
* review / finalize / payslip preview / proof links

### 10.4 Expenses UI

* table view
* category filter
* receipt preview

### 10.5 Exports UI

* month-end pack generation
* ZIP download
* manifest preview

---

## 11. Automation Design

### 11.1 Daily Automation

목표:

* overdue invoice 확인
* unpaid payroll / missing proof 확인
* missing receipts / attachments 확인
* pending reconciliations 확인

실행 예시:

* `acct automation daily`

출력:

* daily summary report JSON / markdown
* optional Slack / Telegram / email notification

### 11.2 Weekly Automation

목표:

* 이번 주 비용 정리
* invoice aging report 생성
* missing evidence reminder
* outstanding client payments 점검

실행 예시:

* `acct automation weekly`

### 11.3 Monthly Automation

목표:

* payroll run 생성 또는 검토 트리거
* recurring invoice 생성
* month-end export pack 생성
* accountant handoff package 준비

실행 예시:

* `acct automation monthly --month 2026-03`

---

## 12. Agent Skills Layer

### 12.1 Skill Philosophy

* skill은 사용자 의도를 안전한 tool invocation으로 변환
* DB 직접 수정 금지
* file write / state transition은 API/CLI만 수행

### 12.2 Candidate Skills

* `create_invoice`
* `issue_invoice`
* `record_invoice_payment`
* `create_payroll_run`
* `finalize_payroll`
* `record_salary_payment`
* `add_expense`
* `attach_evidence`
* `prepare_month_end_pack`
* `run_daily_review`
* `run_weekly_review`
* `run_monthly_close`

### 12.3 Claude Code / Codex Roles

* Claude Code: documentation, orchestration, refactor, test scaffolding, summary generation
* Codex: implementation acceleration, CRUD scaffolding, migration drafts, CLI boilerplate

---

## 13. Integrity and Safety Controls

### 13.1 State Machines

* invalid transition 방지
* draft → finalized → paid 순서 강제

### 13.2 Idempotency Keys

* issue / finalize / export 명령의 중복 실행 보호

### 13.3 Audit Logs

* 모든 상태 변경 기록

### 13.4 Checksums and Versioning

* 생성 문서 hash 저장
* 문서 재생성 시 version 관리

### 13.5 Manual Review Gates

* payroll finalize 전 review 단계
* export pack 생성 전 validation summary 제공

---

## 14. Example Workflows

### 14.1 Monthly Invoice Workflow

1. recurring invoice draft 생성
2. line item 검토
3. issue command 실행
4. PDF 생성
5. client 전송
6. payment 수신 후 mark paid
7. tx hash / bank proof 첨부

### 14.2 First-Month Payroll Workflow

1. payroll run 생성 with issue date
2. prorated salary 계산
3. SDL 계산
4. payslip PDF 생성
5. review
6. finalize
7. payment 실행
8. transfer proof 첨부

### 14.3 Month-End Handoff Workflow

1. expenses / invoices / payroll completeness check
2. missing evidence report 생성
3. export pack 생성
4. ZIP + manifest 저장
5. accountant 전달

---

## 15. MVP Milestones

### Phase 1

* DB schema
* invoice CRUD + PDF
* payroll run + payslip
* file attachment
* audit log

### Phase 2

* payments + crypto metadata
* expense ledger
* month-end export pack
* thin frontend dashboard

### Phase 3

* recurring invoice
* daily/weekly/monthly automation
* skill wrappers
* notification integration

---

## 16. Open Questions

* multi-currency를 MVP에서 어디까지 지원할 것인가?
* crypto payment valuation source는 어떻게 고정할 것인가?
* PDF 템플릿 커스터마이징 범위를 어디까지 허용할 것인가?
* accountant handoff format을 3E 기준으로 맞출 것인가, generic CSV pack으로 갈 것인가?
* auth는 local admin only로 시작할 것인가?

---

## 17. Recommended Next Step

다음 단계는 문서 작성이 아니라 바로 **implementation planning**으로 내려가는 것이다.

우선순위:

1. MVP 범위 freeze
2. DB schema 확정
3. CLI command surface 확정
4. invoice/payroll PDF 템플릿 정의
5. month-end export pack 포맷 정의
6. Claude Code / Codex용 task breakdown 작성

