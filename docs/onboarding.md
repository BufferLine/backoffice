# Onboarding

First-time setup guide for Backoffice. Follow these steps after the server is running.

## Prerequisites

- Server is running (see [Server Setup](server-setup.md) for production, or [Development](development.md) for local)
- `acct` CLI installed: `pip install "git+https://github.com/YOUR_ORG/backoffice.git#subdirectory=cli"`

**Note for AI agents**: Run `acct guide` to get conversational help through the setup process.

---

## Step 1: Initialize the System

Run `acct init` to register your company and get a one-time admin setup link.

```bash
acct init --api-url https://your-domain.com
```

You will be prompted for:
- **Company name** — your legal entity name (e.g. "Acme Pte Ltd")
- **Jurisdiction** — `SG` for Singapore (default), `KR` for Korea, etc.
- **UEN** — Singapore Unique Entity Number (optional, can be added later)

The command prints a one-time setup URL:

```
Open this link in your browser to create your admin account:

  https://your-domain.com/setup/abc123...

This link expires in 1 hour and can only be used once.
```

### Quick path (CLI-only, no browser)

If you prefer to stay in the terminal and skip the browser entirely, pass admin credentials directly:

```bash
acct init \
  --company-name "Acme Pte Ltd" \
  --jurisdiction SG \
  --uen 202312345A \
  --api-url https://your-domain.com \
  --admin-email admin@acme.com \
  --admin-password "YourSecurePassword" \
  --admin-name "Admin User"
```

When `--admin-email`, `--admin-password`, and `--admin-name` are all provided, the admin account is created immediately and no browser URL is printed.

---

## Step 2: Create Your Admin Account

Open the setup URL in a browser. You will be asked to set:
- Admin email address
- Password

After completing the form, your admin account is created and the setup URL is consumed.

---

## Step 3: Login via CLI

```bash
acct login --email you@company.com --api-url https://your-domain.com
```

Enter your password when prompted. Your token is stored in `~/.acct/credentials.json`.

Verify:

```bash
acct whoami
```

---

## Step 3b: Create Chart of Accounts (Optional)

Before processing transactions, optionally set up your chart of accounts:

```bash
acct account create \
  --name "DBS Operating" \
  --type bank \
  --account-class asset \
  --currency SGD \
  --institution "DBS Bank" \
  --opening-balance-date 2026-01-01

acct account create \
  --name "Business Expenses" \
  --type virtual \
  --account-class expense \
  --currency SGD \
  --opening-balance-date 2026-01-01
```

Account types: `bank`, `crypto_wallet`, `cash`, `virtual`.
Account classes: `asset`, `liability`, `equity`, `revenue`, `expense`.

---

## Step 4: Configure Company Settings

Update your company profile with bank details, GST registration, and branding.

```bash
# Core identity
acct settings update \
  --company-name "Acme Pte Ltd" \
  --uen 202312345A \
  --address "10 Anson Road #05-01, Singapore 079903" \
  --billing-email billing@acme.com

# Bank details (printed on invoices)
acct settings update \
  --bank-name "DBS Bank" \
  --bank-account 123-456789-0 \
  --bank-swift DBSSSGSG

# GST (if registered)
acct settings update \
  --gst-registered true \
  --gst-rate 0.09

# Default invoice payment terms
acct settings update --payment-terms 30
```

### Upload logo and stamp

```bash
acct settings upload-logo  /path/to/logo.png
acct settings upload-stamp /path/to/stamp.png
```

Supported formats: PNG or JPEG, recommended size 400×200px for logo, 200×200px for stamp.

---

## Step 5: Set Up Payment Methods

Register at least one payment method so it can appear on invoices.

```bash
# Bank transfer
acct payment-method add \
  --name "DBS SGD" \
  --type bank_transfer \
  --currency SGD \
  --bank-name "DBS Bank" \
  --bank-account 123-456789-0 \
  --bank-swift DBSSSGSG \
  --default

# PayNow (Singapore)
acct payment-method add \
  --name "PayNow" \
  --type paynow \
  --currency SGD \
  --uen 202312345A

# Crypto (USDC on Ethereum)
acct payment-method add \
  --name "USDC" \
  --type crypto \
  --currency USD \
  --wallet 0xYourWalletAddress \
  --chain ethereum
```

List registered methods:

```bash
acct payment-method list
```

---

## Step 6: Add Your First Client

```bash
acct client create \
  --name "Client Corp Pte Ltd" \
  --email accounts@clientcorp.com \
  --currency SGD \
  --payment-terms 30
```

Note the client ID from the output — you will need it when creating invoices.

```bash
acct client list
```

---

## Step 7: Create Your First Invoice

```bash
# Create draft
acct invoice create \
  --client <client-id> \
  --currency SGD \
  --payment-method <payment-method-id>

# Add line items
acct invoice add-item <invoice-id> \
  --desc "Consulting services — March 2026" \
  --qty 1 \
  --price 5000 \
  --tax-code SR

# Review
acct invoice show <invoice-id>

# Issue (generates PDF)
acct invoice issue <invoice-id>

# Download PDF
acct invoice download <invoice-id>
```

---

## Step 8: Add Employees (if running payroll)

```bash
acct employee add \
  --name "Jane Smith" \
  --salary 8000 \
  --currency SGD \
  --start-date 2026-01-01 \
  --pass-type EP
```

Pass types: `EP` (Employment Pass), `SP` (S Pass), `WP` (Work Permit), `PR` (Permanent Resident), `Citizen`.

---

## Monthly Workflow

Once set up, the typical monthly cycle is:

```bash
# 1. Check what's due this month
acct todo summary

# 2. Run payroll for each employee
acct payroll run --employee <id> --month 2026-03
acct payroll review <id>
acct payroll finalize <id>

# 3. Issue recurring invoices (or create new ones)
acct invoice create ...

# 4. Record payments received
acct payment record --type bank_transfer --entity invoice:<id> --amount 5000 --currency SGD --date 2026-03-20

# 5. Mark invoices paid
acct invoice mark-paid <invoice-id> --payment-id <payment-id>

# 6. Export for accountant
acct export validate --month 2026-03
acct export month-end --month 2026-03
```
