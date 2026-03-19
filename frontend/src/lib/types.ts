// Auth
export interface User {
  id: string;
  email: string;
  name: string;
  is_active: boolean;
  roles: Role[];
  permissions: string[];
  created_at: string;
  updated_at: string;
}

export interface Role {
  id: string;
  name: string;
  description: string | null;
  is_system: boolean;
}

export interface Permission {
  id: string;
  domain: string;
  action: string;
  description: string | null;
}

// Client
export interface Client {
  id: string;
  legal_name: string;
  billing_email: string | null;
  billing_address: string | null;
  default_currency: string | null;
  payment_terms_days: number | null;
  preferred_payment_method: string | null;
  wallet_address: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

// Invoice
export type InvoiceStatus = "draft" | "issued" | "paid" | "cancelled";

export interface Invoice {
  id: string;
  invoice_number: string;
  client_id: string;
  client?: Client;
  issue_date: string | null;
  due_date: string | null;
  currency: string;
  subtotal_amount: string;
  tax_rate: string | null;
  tax_amount: string;
  total_amount: string;
  status: InvoiceStatus;
  description: string | null;
  payment_method: string | null;
  wallet_address: string | null;
  line_items: InvoiceLineItem[];
  created_at: string;
  updated_at: string;
}

export interface InvoiceLineItem {
  id: string;
  invoice_id: string;
  description: string;
  quantity: string;
  unit_price: string;
  amount: string;
  sort_order: number;
}

export interface RecurringInvoiceRule {
  id: string;
  client_id: string;
  frequency: "monthly" | "quarterly" | "yearly";
  day_of_month: number;
  currency: string;
  line_items_json: InvoiceLineItem[];
  is_active: boolean;
  next_issue_date: string;
}

// Employee
export interface Employee {
  id: string;
  name: string;
  email: string | null;
  base_salary: string;
  salary_currency: string;
  start_date: string;
  end_date: string | null;
  work_pass_type: string;
  tax_residency: string;
  status: "active" | "terminated";
  created_at: string;
  updated_at: string;
}

// Payroll
export type PayrollStatus = "draft" | "reviewed" | "finalized" | "paid";

export interface PayrollRun {
  id: string;
  employee_id: string;
  employee?: Employee;
  month: string;
  start_date: string;
  end_date: string;
  days_in_month: number;
  days_worked: number;
  monthly_base_salary: string;
  currency: string;
  prorated_gross_salary: string;
  total_deductions: string;
  net_salary: string;
  status: PayrollStatus;
  deductions: PayrollDeduction[];
  paid_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PayrollDeduction {
  id: string;
  payroll_run_id: string;
  deduction_type: string;
  description: string | null;
  amount: string;
  rate: string | null;
  cap_amount: string | null;
  sort_order: number;
}

// Expense
export type ExpenseStatus = "draft" | "confirmed" | "reimbursed";

export interface Expense {
  id: string;
  expense_date: string;
  vendor: string | null;
  category: string | null;
  currency: string;
  amount: string;
  payment_method: string | null;
  reimbursable: boolean;
  status: ExpenseStatus;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

// Payment
export interface Payment {
  id: string;
  payment_type: "bank_transfer" | "crypto";
  related_entity_type: string | null;
  related_entity_id: string | null;
  payment_date: string;
  currency: string;
  amount: string;
  fx_rate_to_sgd: string | null;
  fx_rate_date: string | null;
  fx_rate_source: string | null;
  sgd_value: string | null;
  tx_hash: string | null;
  chain_id: string | null;
  bank_reference: string | null;
  notes: string | null;
  created_at: string;
}

// Bank Reconciliation
export type MatchStatus =
  | "unmatched"
  | "auto_matched"
  | "manual_matched"
  | "ignored";

export interface BankTransaction {
  id: string;
  source: string;
  source_tx_id: string;
  tx_date: string;
  amount: string;
  currency: string;
  counterparty: string | null;
  reference: string | null;
  description: string | null;
  matched_payment_id: string | null;
  match_status: MatchStatus;
  match_confidence: string | null;
  imported_at: string;
}

// File
export interface FileRecord {
  id: string;
  storage_key: string;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  checksum_sha256: string;
  uploaded_at: string;
  linked_entity_type: string | null;
  linked_entity_id: string | null;
}

// Export
export interface ExportPack {
  id: string;
  month: string;
  version: number;
  generated_at: string;
  zip_file_id: string;
  status: "generating" | "complete" | "failed";
  notes: string | null;
  validation_summary_json: Record<string, unknown> | null;
}

// Currency
export interface Currency {
  code: string;
  name: string;
  symbol: string;
  display_precision: number;
  is_crypto: boolean;
  chain_id: string | null;
  is_active: boolean;
}

// Company Settings
export interface CompanySettings {
  id: string;
  legal_name: string;
  uen: string | null;
  address: string | null;
  billing_email: string | null;
  bank_name: string | null;
  bank_account_number: string | null;
  bank_swift_code: string | null;
  default_currency: string;
  default_payment_terms_days: number;
  gst_registered: boolean;
  gst_rate: string | null;
  jurisdiction: string;
}

// API responses
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
}
