"""crypto receipt ledger: widen journal currency, link journals to invoices/payments/fx

Revision ID: 4a7c91e2d5b6
Revises: c3d4e5f6a7b8
Create Date: 2026-11-05 09:00:00.000000

- ``journal_lines.currency`` was VARCHAR(3), which cannot hold stablecoin codes
  such as ``USDC``/``USDT``. Widen it to match ``currencies.code`` (VARCHAR(10)).
- ``invoices.journal_entry_id``: the accounts-receivable entry posted at issue.
- ``payments.journal_entry_id``: the receipt entry posted when a payment settles an invoice.
- ``fx_conversions.bank_transaction_id``: the bank deposit the conversion landed as,
  so the deposit is reconciled by the conversion instead of being booked twice.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '4a7c91e2d5b6'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'journal_lines',
        'currency',
        existing_type=sa.String(length=3),
        type_=sa.String(length=10),
        existing_nullable=False,
    )

    op.add_column(
        'invoices',
        sa.Column('journal_entry_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'fk_invoices_journal_entry_id', 'invoices', 'journal_entries',
        ['journal_entry_id'], ['id'], ondelete='SET NULL',
    )

    op.add_column(
        'payments',
        sa.Column('journal_entry_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'fk_payments_journal_entry_id', 'payments', 'journal_entries',
        ['journal_entry_id'], ['id'], ondelete='SET NULL',
    )

    op.add_column(
        'fx_conversions',
        sa.Column('bank_transaction_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'fk_fx_conversions_bank_transaction_id', 'fx_conversions', 'bank_transactions',
        ['bank_transaction_id'], ['id'], ondelete='SET NULL',
    )
    op.create_index(
        'uq_fx_conversions_bank_transaction_id_not_null',
        'fx_conversions',
        ['bank_transaction_id'],
        unique=True,
        postgresql_where=sa.text('bank_transaction_id IS NOT NULL'),
    )


def downgrade() -> None:
    # Narrowing journal_lines.currency back to VARCHAR(3) fails once any USDC/USDT
    # journal line exists; fail early with a clear message instead of a type error.
    bind = op.get_bind()
    long_codes = bind.execute(sa.text("SELECT COUNT(*) FROM journal_lines WHERE length(currency) > 3")).scalar()
    if long_codes:
        raise RuntimeError(
            f"Cannot downgrade: {long_codes} journal lines use currency codes longer than 3 characters (e.g. USDC)"
        )
    op.drop_index('uq_fx_conversions_bank_transaction_id_not_null', table_name='fx_conversions')
    op.drop_constraint('fk_fx_conversions_bank_transaction_id', 'fx_conversions', type_='foreignkey')
    op.drop_column('fx_conversions', 'bank_transaction_id')
    op.drop_constraint('fk_payments_journal_entry_id', 'payments', type_='foreignkey')
    op.drop_column('payments', 'journal_entry_id')
    op.drop_constraint('fk_invoices_journal_entry_id', 'invoices', type_='foreignkey')
    op.drop_column('invoices', 'journal_entry_id')
    op.alter_column(
        'journal_lines',
        'currency',
        existing_type=sa.String(length=10),
        type_=sa.String(length=3),
        existing_nullable=False,
    )
