import csv
import io
from datetime import date, datetime
from decimal import Decimal

from app.export_formatters.base import ExportFormatter


class GenericCsvFormatter(ExportFormatter):
    def format_invoices(self, invoices: list[dict]) -> bytes:
        return self._to_csv(invoices, [
            "invoice_number", "client_name", "issue_date", "due_date",
            "currency", "subtotal_amount", "tax_amount", "total_amount",
            "status", "payment_method",
        ])

    def format_payroll(self, payroll_runs: list[dict]) -> bytes:
        return self._to_csv(payroll_runs, [
            "employee_name", "month", "start_date", "end_date",
            "days_worked", "days_in_month", "currency",
            "monthly_base_salary", "prorated_gross_salary",
            "total_deductions", "net_salary", "status",
        ])

    def format_expenses(self, expenses: list[dict]) -> bytes:
        return self._to_csv(expenses, [
            "expense_date", "vendor", "category", "currency",
            "amount", "payment_method", "reimbursable", "status", "notes",
        ])

    def format_payments(self, payments: list[dict]) -> bytes:
        return self._to_csv(payments, [
            "payment_date", "payment_type", "currency", "amount",
            "fx_rate_to_sgd", "sgd_value", "related_entity_type",
            "related_entity_id", "tx_hash", "bank_reference",
        ])

    def _to_csv(self, rows: list[dict], columns: list[str]) -> bytes:
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            clean_row = {}
            for k, v in row.items():
                if isinstance(v, Decimal):
                    clean_row[k] = str(v)
                elif isinstance(v, (date, datetime)):
                    clean_row[k] = v.isoformat()
                else:
                    clean_row[k] = v
            writer.writerow(clean_row)
        return output.getvalue().encode("utf-8")
