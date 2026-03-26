"""enable row level security on all tables

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-03-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = 'd6e7f8a9b0c1'
down_revision: Union[str, None] = 'c5d6e7f8a9b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = [
    "accounts",
    "api_tokens",
    "audit_logs",
    "bank_transactions",
    "change_logs",
    "clients",
    "company_settings",
    "currencies",
    "employees",
    "expenses",
    "export_packs",
    "files",
    "integration_configs",
    "integration_events",
    "integration_sync_states",
    "invoice_line_items",
    "invoice_payment_methods",
    "invoices",
    "loans",
    "payment_allocations",
    "payment_methods",
    "payments",
    "payroll_deductions",
    "payroll_runs",
    "permissions",
    "recurring_commitments",
    "recurring_invoice_rules",
    "role_permissions",
    "roles",
    "setup_tokens",
    "task_instances",
    "task_templates",
    "transactions",
    "user_roles",
    "users",
]


def upgrade() -> None:
    conn = op.get_bind()
    for table in TABLES:
        conn.execute(text(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY'))


def downgrade() -> None:
    conn = op.get_bind()
    for table in TABLES:
        conn.execute(text(f'ALTER TABLE public."{table}" DISABLE ROW LEVEL SECURITY'))
