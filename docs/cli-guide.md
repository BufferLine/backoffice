# CLI Guide

Full reference for the `acct` command-line interface.

## Installation

```bash
pip install "git+https://github.com/YOUR_ORG/backoffice.git#subdirectory=cli"
```

Verify:

```bash
acct --help
```

---

## General

### `acct guide`

Print agent guide for AI agents.

```bash
acct guide
```

---

## Authentication

### `acct init`

Initialize the backoffice system and get the admin setup URL.

```bash
acct init [--api-url URL] [--admin-email EMAIL] [--admin-password PASSWORD] [--admin-name NAME]
```

Prompts for company name, jurisdiction, and UEN. Prints a one-time browser URL to create the admin account.

```bash
acct init --api-url https://backoffice.example.com
```

Pass `--admin-email`, `--admin-password`, and `--admin-name` to create the admin account immediately without opening a browser:

```bash
acct init \
  --api-url https://backoffice.example.com \
  --admin-email admin@example.com \
  --admin-password "YourSecurePassword" \
  --admin-name "Admin User"
```

### `acct login`

Login and store credentials locally.

```bash
acct login [--email EMAIL] [--api-url URL]
```

```bash
acct login --email admin@example.com --api-url https://backoffice.example.com
```

Prompts for password. Token is saved to `~/.acct/credentials.json`.

### `acct whoami`

Show the current logged-in user.

```bash
acct whoami
```

### `acct logout`

Remove stored credentials.

```bash
acct logout
```

---

## Clients

### `acct client create`

```bash
acct client create --name NAME [--email EMAIL] [--address ADDR] [--currency CODE] [--payment-terms DAYS]
```

```bash
acct client create --name "Acme Corp" --email accounts@acme.com --currency SGD --payment-terms 30
```

### `acct client list`

```bash
acct client list
```

### `acct client show`

```bash
acct client show <client-id>
```

---

## Invoices

### `acct invoice create`

Create a new draft invoice.

```bash
acct invoice create --client CLIENT_ID [--currency CODE] [--description TEXT] [--payment-method ID ...]
```

```bash
acct invoice create --client abc123 --currency SGD --payment-method pm-id-1 --payment-method pm-id-2
```

### `acct invoice add-item`

Add a line item to a draft invoice.

```bash
acct invoice add-item INVOICE_ID --desc TEXT --qty NUM --price NUM [--tax-code CODE] [--tax-rate RATE]
```

| Option | Description |
|--------|-------------|
| `--tax-code` | `SR` (Standard Rate 9%), `ZR` (Zero-Rated), `ES` (Exempt), `NT` (Not Taxable). Default: `SR` |
| `--tax-rate` | Override rate, e.g. `0.09` for 9% |

```bash
acct invoice add-item inv123 --desc "Consulting" --qty 1 --price 5000 --tax-code SR
```

### `acct invoice edit`

Edit a draft invoice.

```bash
acct invoice edit INVOICE_ID [--description TEXT] [--due-date YYYY-MM-DD]
```

### `acct invoice issue`

Issue a draft invoice. Assigns invoice number and generates PDF.

```bash
acct invoice issue INVOICE_ID
```

### `acct invoice mark-paid`

Mark an issued invoice as paid.

```bash
acct invoice mark-paid INVOICE_ID --payment-id PAYMENT_ID
```

### `acct invoice cancel`

Cancel a draft or issued invoice.

```bash
acct invoice cancel INVOICE_ID
```

### `acct invoice list`

```bash
acct invoice list [--status draft|issued|paid|cancelled]
```

### `acct invoice show`

```bash
acct invoice show INVOICE_ID
```

### `acct invoice download`

Download the invoice PDF.

```bash
acct invoice download INVOICE_ID [-o OUTPUT_PATH]
```

### `acct invoice regenerate-pdf`

Regenerate PDF with current company branding (logo, stamp, colors).

```bash
acct invoice regenerate-pdf INVOICE_ID
```

### `acct invoice attach`

Attach a file to an invoice.

```bash
acct invoice attach INVOICE_ID /path/to/file.pdf
```

---

## Payroll

### `acct employee add`

Register a new employee.

```bash
acct employee add --name NAME --salary AMOUNT --start-date YYYY-MM-DD --pass-type TYPE [--currency CODE]
```

Pass types: `EP`, `SP`, `WP`, `PR`, `Citizen`.

```bash
acct employee add --name "John Doe" --salary 9500 --start-date 2026-03-01 --pass-type EP
```

### `acct employee list`

```bash
acct employee list
```

### `acct employee show`

```bash
acct employee show EMPLOYEE_ID
```

### `acct payroll run`

Create a payroll run for an employee. Use `--start-date` for prorated first months.

```bash
acct payroll run --employee EMPLOYEE_ID --month YYYY-MM [--start-date YYYY-MM-DD]
```

```bash
# Full month
acct payroll run --employee emp123 --month 2026-03

# Prorated (joined mid-month)
acct payroll run --employee emp123 --month 2026-03 --start-date 2026-03-15
```

### `acct payroll review`

Move a draft payroll run to reviewed state.

```bash
acct payroll review PAYROLL_ID
```

### `acct payroll finalize`

Finalize a reviewed payroll run. Generates payslip PDF.

```bash
acct payroll finalize PAYROLL_ID
```

### `acct payroll mark-paid`

Mark a finalized payroll run as paid.

```bash
acct payroll mark-paid PAYROLL_ID --payment-id PAYMENT_ID
```

### `acct payroll edit`

Edit a draft payroll run (recalculates proration).

```bash
acct payroll edit PAYROLL_ID [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD]
```

### `acct payroll delete`

Delete a payroll run. Finalized runs require a reason.

```bash
acct payroll delete PAYROLL_ID [--reason TEXT]
```

### `acct payroll download`

Download the payslip PDF.

```bash
acct payroll download PAYROLL_ID [-o OUTPUT_PATH]
```

### `acct payroll regenerate-pdf`

Regenerate payslip PDF with current branding.

```bash
acct payroll regenerate-pdf PAYROLL_ID
```

### `acct payroll list`

```bash
acct payroll list [--month YYYY-MM]
```

### `acct payroll show`

```bash
acct payroll show PAYROLL_ID
```

---

## Expenses

### `acct expense add`

Record a new expense.

```bash
acct expense add --date YYYY-MM-DD --vendor NAME --category CAT --amount NUM [--currency CODE] [--description TEXT]
```

```bash
acct expense add --date 2026-03-15 --vendor AWS --category cloud --amount 145 --currency USD
```

### `acct expense confirm`

Confirm a pending expense.

```bash
acct expense confirm EXPENSE_ID
```

### `acct expense reimburse`

Mark an expense as reimbursed.

```bash
acct expense reimburse EXPENSE_ID --payment-id PAYMENT_ID
```

### `acct expense list`

```bash
acct expense list [--month YYYY-MM] [--category CAT]
```

### `acct expense attach`

Attach a receipt to an expense.

```bash
acct expense attach EXPENSE_ID /path/to/receipt.pdf
```

---

## Payments

### `acct payment record`

Record a payment against an invoice, payroll run, or expense.

```bash
acct payment record --type TYPE --entity ENTITY_REF --amount NUM --currency CODE [--date YYYY-MM-DD] [--reference REF] [--tx-hash HASH] [--chain CHAIN]
```

| Option | Description |
|--------|-------------|
| `--type` | `bank_transfer`, `crypto`, or `cash` |
| `--entity` | Entity reference, e.g. `invoice:uuid`, `payroll_run:uuid`, `expense:uuid` |
| `--tx-hash` | Crypto transaction hash |
| `--chain` | Blockchain network (e.g. `ethereum`, `polygon`) |
| `--reference` | Bank reference number |

```bash
# Bank transfer for invoice
acct payment record \
  --type bank_transfer \
  --entity invoice:abc123 \
  --amount 5000 \
  --currency SGD \
  --date 2026-03-20 \
  --reference TXN20260320

# Crypto payment
acct payment record \
  --type crypto \
  --entity invoice:abc123 \
  --amount 3750 \
  --currency USD \
  --tx-hash 0xabc... \
  --chain ethereum
```

### `acct payment allocate`

Allocate a payment towards a loan repayment.

```bash
acct payment allocate --payment-id PAYMENT_ID --loan-id LOAN_ID --amount NUM
```

### `acct payment list`

```bash
acct payment list [--entity-type invoice|payroll_run|expense]
```

### `acct payment show`

```bash
acct payment show PAYMENT_ID
```

---

## Payment Methods

### `acct payment-method add`

Register a payment method (shown on invoices).

```bash
acct payment-method add --name NAME --type TYPE --currency CODE [options]
```

| Option | Description |
|--------|-------------|
| `--type` | `bank_transfer`, `crypto`, `paynow` |
| `--bank-name` | Bank name |
| `--bank-account` | Account number |
| `--bank-swift` | SWIFT/BIC code |
| `--wallet` | Wallet address (crypto) |
| `--chain` | Chain ID (crypto) |
| `--uen` | UEN number (PayNow) |
| `--default` | Set as default for this currency |

```bash
acct payment-method add --name "DBS SGD" --type bank_transfer --currency SGD \
  --bank-name "DBS Bank" --bank-account 123-456789-0 --bank-swift DBSSSGSG --default
```

### `acct payment-method update`

```bash
acct payment-method update METHOD_ID [--name NAME] [--nickname TEXT] [--default BOOL] ...
```

### `acct payment-method list`

```bash
acct payment-method list
```

### `acct payment-method show`

```bash
acct payment-method show METHOD_ID
```

### `acct payment-method deactivate`

```bash
acct payment-method deactivate METHOD_ID
```

---

## Accounts & Transactions

### `acct account create`

```bash
acct account create --name NAME --type TYPE --opening-balance-date YYYY-MM-DD \
  [--currency CODE] [--institution NAME] [--account-number NUM] \
  [--wallet-address ADDR] [--opening-balance AMOUNT]
```

Account types: `bank`, `crypto_wallet`, `cash`, `virtual`.

```bash
acct account create \
  --name "DBS SGD" \
  --type bank \
  --currency SGD \
  --institution "DBS Bank" \
  --opening-balance 50000 \
  --opening-balance-date 2026-01-01
```

### `acct account list`

```bash
acct account list [--page N] [--per-page N]
```

### `acct account balance`

Show balance breakdown for an account.

```bash
acct account balance ACCOUNT_ID
```

### `acct transaction create`

```bash
acct transaction create --account ACCOUNT_ID --direction in|out --amount NUM \
  --date YYYY-MM-DD --category CAT [--currency CODE] [--counterparty NAME] \
  [--description TEXT] [--reference REF] [--status pending|confirmed]
```

### `acct transaction confirm`

```bash
acct transaction confirm TX_ID
```

### `acct transaction cancel`

```bash
acct transaction cancel TX_ID
```

### `acct transaction list`

```bash
acct transaction list [--account ACCOUNT_ID] [--category CAT] [--status STATUS] [--from YYYY-MM-DD] [--to YYYY-MM-DD]
```

---

## Journal

### `acct journal create`

Create a new journal entry with debit and credit sides.

```bash
acct journal create --date YYYY-MM-DD --debit ACCT_ID:AMOUNT --credit ACCT_ID:AMOUNT [--currency CODE] [--description TEXT] [--confirm/--no-confirm]
```

```bash
acct journal create \
  --date 2026-03-20 \
  --debit acc-expense:1500 \
  --credit acc-bank:1500 \
  --currency SGD \
  --description "Office supplies" \
  --confirm
```

### `acct journal list`

```bash
acct journal list [--page N] [--confirmed/--unconfirmed] [--from YYYY-MM-DD] [--to YYYY-MM-DD]
```

### `acct journal show`

```bash
acct journal show ENTRY_ID
```

### `acct journal confirm`

Confirm a pending journal entry.

```bash
acct journal confirm ENTRY_ID
```

### `acct journal delete`

Delete a journal entry.

```bash
acct journal delete ENTRY_ID
```

---

## Reports

### `acct report trial-balance`

Generate a trial balance report as of a specific date.

```bash
acct report trial-balance [--date YYYY-MM-DD] [--include-unconfirmed]
```

```bash
acct report trial-balance --date 2026-03-31
acct report trial-balance --date 2026-03-31 --include-unconfirmed
```

---

## Tasks & Todo

### `acct todo summary`

Show pending/in-progress/completed/overdue counts for the current (or specified) period.

```bash
acct todo summary [--period YYYY-MM|YYYY-QN|YYYY]
```

```bash
acct todo summary
acct todo summary --period 2026-03
```

### `acct todo list`

```bash
acct todo list [--period YYYY-MM] [--status STATUS] [--category CAT]
```

### `acct todo complete`

```bash
acct todo complete TASK_ID [--notes TEXT]
```

### `acct todo skip`

```bash
acct todo skip TASK_ID [--notes TEXT]
```

### `acct todo add`

Create an ad-hoc task.

```bash
acct todo add "Task title" [--description TEXT] [--category CAT] [--priority high|medium|low] [--due-date YYYY-MM-DD] [--period YYYY-MM]
```

### `acct todo upcoming`

```bash
acct todo upcoming [--days N]    # default: 30
```

### `acct todo overdue`

```bash
acct todo overdue
```

### `acct todo note`

```bash
acct todo note TASK_ID "Note text"
```

### `acct todo template-add`

Create a recurring task template.

```bash
acct todo template-add "Template title" --frequency FREQ [--category CAT] [--due-day N] [--priority LEVEL]
```

Frequency: `monthly`, `quarterly`, `yearly`, `once`.

```bash
acct todo template-add "CPF payment" --frequency monthly --category payroll --due-day 14 --priority high
```

### `acct todo template-list`

```bash
acct todo template-list [--category CAT]
```

### `acct todo generate`

Generate task instances from templates for the current or specified period.

```bash
acct todo generate [--since YYYY-MM-DD]
```

### `acct todo archive`

Archive completed or skipped tasks older than a given date.

```bash
acct todo archive [--before YYYY-MM-DD]
```

---

## Exports

### `acct export validate`

Check data completeness before generating the month-end pack.

```bash
acct export validate --month YYYY-MM
```

Returns a summary of any missing evidence, unconfirmed expenses, or unissued invoices.

### `acct export month-end`

Generate the month-end export pack (ZIP with CSVs, PDFs, and manifest).

```bash
acct export month-end --month YYYY-MM [--force]
```

Use `--force` to proceed despite validation warnings.

### `acct export list`

```bash
acct export list
```

### `acct export download`

```bash
acct export download EXPORT_ID [-o OUTPUT_DIR]    # default: ./exports
```

---

## Settings

### `acct settings show`

```bash
acct settings show
```

### `acct settings update`

```bash
acct settings update [--company-name NAME] [--uen UEN] [--address ADDR] [--billing-email EMAIL]
  [--bank-name NAME] [--bank-account NUM] [--bank-swift CODE]
  [--default-currency CODE] [--payment-terms DAYS]
  [--gst-registered BOOL] [--gst-rate RATE]
  [--jurisdiction CODE] [--primary-color HEX] [--accent-color HEX] [--font-family FONT]
```

### `acct settings upload-logo`

```bash
acct settings upload-logo /path/to/logo.png
```

### `acct settings upload-stamp`

```bash
acct settings upload-stamp /path/to/stamp.png
```

### `acct currency add`

```bash
acct currency add --code CODE --name NAME --symbol SYM [--precision N]
```

```bash
acct currency add --code EUR --name Euro --symbol € --precision 2
```

### `acct currency list`

```bash
acct currency list
```

---

## Changelog

### `acct changelog history`

Show field-level change history for any entity.

```bash
acct changelog history ENTITY_TYPE ENTITY_ID [--field FIELD_NAME]
```

```bash
acct changelog history invoice abc123
acct changelog history employee emp456 --field base_salary
```

### `acct changelog period`

Show all changes in a date range.

```bash
acct changelog period START_DATE END_DATE [--entity-type TYPE]
```

```bash
acct changelog period 2026-03-01 2026-03-31 --entity-type invoice
```

---

## Bank Statements

### `acct bank statement-upload`

Upload a bank statement CSV for reconciliation.

```bash
acct bank statement-upload /path/to/statement.csv --source SOURCE
```

Sources: `airwallex`, `generic`.

### `acct bank tx-list`

```bash
acct bank tx-list [--status unmatched|matched|ignored]
```

### `acct bank tx-reconcile`

Reconcile a bank transaction by creating a journal entry automatically (debit/credit based on deposit/withdrawal).

```bash
acct bank tx-reconcile TX_ID --bank-account ACCOUNT_ID --contra-account ACCOUNT_ID [--description TEXT] [--no-confirm]
```

```bash
acct bank tx-reconcile tx-abc123 \
  --bank-account acc-bank-dbs \
  --contra-account acc-expense \
  --description "Office supplies reimbursement"
```

---

## Loans

### `acct loan create`

Create a new director/shareholder loan.

```bash
acct loan create --borrower NAME --principal AMOUNT --currency CODE --rate RATE --start-date YYYY-MM-DD [--interest-type simple|compound]
```

### `acct loan list`

```bash
acct loan list [--status active|repaid|written-off]
```

### `acct loan show`

```bash
acct loan show LOAN_ID
```

### `acct loan edit`

Edit a draft loan record.

```bash
acct loan edit LOAN_ID [--rate RATE] [--notes TEXT]
```

### `acct loan balance`

Show outstanding balance and accrued interest.

```bash
acct loan balance LOAN_ID
```

### `acct loan mark-repaid`

Mark a loan as fully repaid.

```bash
acct loan mark-repaid LOAN_ID
```

### `acct loan write-off`

Write off an unrecoverable loan.

```bash
acct loan write-off LOAN_ID [--reason TEXT]
```

### `acct loan generate-pdf`

Generate the loan agreement PDF.

```bash
acct loan generate-pdf LOAN_ID [-o OUTPUT_PATH]
```

### `acct loan generate-statement`

Generate a loan statement PDF (repayment history + outstanding balance).

```bash
acct loan generate-statement LOAN_ID [-o OUTPUT_PATH]
```

### `acct loan generate-discharge`

Generate a discharge letter PDF (issued when loan is fully repaid).

```bash
acct loan generate-discharge LOAN_ID [-o OUTPUT_PATH]
```

### `acct loan download`

Download the most recent loan document PDF.

```bash
acct loan download LOAN_ID [--type agreement|statement|discharge] [-o OUTPUT_PATH]
```

---

## Integrations

### `acct integration list`

Show configured integration providers and their sync status.

```bash
acct integration list
```

### `acct integration events`

View the integration event log for a provider.

```bash
acct integration events PROVIDER [--limit N]
```

```bash
acct integration events airwallex --limit 20
```
