"""bank_transactions.journal_entry_id: the journal entry a bank row is reconciled into

Revision ID: 8e3f1c5a9b27
Revises: 7d2e8b41c9f3
Create Date: 2026-11-24 18:00:00.000000

Lets several synced rows (e.g. the many fills of one Coinbase order) be reconciled
into a single journal entry posted separately, instead of one generated entry per row.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '8e3f1c5a9b27'
down_revision: Union[str, None] = '7d2e8b41c9f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('bank_transactions', sa.Column('journal_entry_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_bank_transactions_journal_entry_id', 'bank_transactions', 'journal_entries',
        ['journal_entry_id'], ['id'], ondelete='SET NULL',
    )
    op.create_index('ix_bank_transactions_journal_entry_id', 'bank_transactions', ['journal_entry_id'])

    # Backfill links for rows reconciled before this column existed, so a later
    # link cannot claim an entry that already accounts for them.
    op.execute(
        """
        UPDATE bank_transactions b SET journal_entry_id = j.id
        FROM journal_entries j
        WHERE b.journal_entry_id IS NULL AND b.match_status = 'reconciled'
          AND j.source_type = 'bank_import' AND j.source_id = b.id
        """
    )
    op.execute(
        """
        UPDATE bank_transactions b SET journal_entry_id = f.journal_entry_id
        FROM fx_conversions f
        WHERE b.journal_entry_id IS NULL AND f.bank_transaction_id = b.id AND f.journal_entry_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index('ix_bank_transactions_journal_entry_id', table_name='bank_transactions')
    op.drop_constraint('fk_bank_transactions_journal_entry_id', 'bank_transactions', type_='foreignkey')
    op.drop_column('bank_transactions', 'journal_entry_id')
