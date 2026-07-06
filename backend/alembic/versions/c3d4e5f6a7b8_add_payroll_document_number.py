"""add payroll_runs.document_number with unique index and backfill

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-06 09:00:00.000000

Payslips get their own document number (``BL-PS-YYYY-NNNN``) assigned at
finalize time. It shares a single series with ``payments.reference_number``
so the payslip PDF and the bank/payment reference always match.

Backfill:
1. Runs already linked to a payment reuse that payment's ``BL-PS`` reference.
2. Any remaining finalized/paid run gets the next number in its year, computed
   across both the backfilled runs and existing payments.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _next_seq(max_ref):
    if max_ref is None:
        return 1
    try:
        return int(max_ref.split("-")[-1]) + 1
    except (ValueError, IndexError):
        return 1


def upgrade() -> None:
    op.add_column('payroll_runs', sa.Column('document_number', sa.String(length=50), nullable=True))
    op.create_index(
        'uq_payroll_runs_document_number_not_null',
        'payroll_runs',
        ['document_number'],
        unique=True,
        postgresql_where=sa.text('document_number IS NOT NULL'),
    )

    bind = op.get_bind()

    # 1. Reuse the linked payment's BL-PS reference where present.
    bind.execute(sa.text(
        """
        UPDATE payroll_runs pr
        SET document_number = p.reference_number
        FROM payments p
        WHERE pr.payment_id = p.id
          AND pr.document_number IS NULL
          AND p.reference_number LIKE 'BL-PS-%'
        """
    ))

    # 2. Assign sequential numbers to remaining finalized/paid runs, per year.
    rows = bind.execute(sa.text(
        """
        SELECT id, EXTRACT(YEAR FROM month)::int AS yr
        FROM payroll_runs
        WHERE document_number IS NULL
          AND status IN ('finalized', 'paid')
        ORDER BY month, created_at
        """
    )).fetchall()

    for run_id, yr in rows:
        prefix = f"BL-PS-{yr}-"
        pay_max = bind.execute(sa.text(
            "SELECT MAX(reference_number) FROM payments WHERE reference_number LIKE :p"
        ), {"p": f"{prefix}%"}).scalar()
        run_max = bind.execute(sa.text(
            "SELECT MAX(document_number) FROM payroll_runs WHERE document_number LIKE :p"
        ), {"p": f"{prefix}%"}).scalar()
        nxt = max(_next_seq(pay_max), _next_seq(run_max))
        bind.execute(sa.text(
            "UPDATE payroll_runs SET document_number = :dn WHERE id = :id"
        ), {"dn": f"{prefix}{nxt:04d}", "id": run_id})


def downgrade() -> None:
    op.drop_index('uq_payroll_runs_document_number_not_null', table_name='payroll_runs')
    op.drop_column('payroll_runs', 'document_number')
