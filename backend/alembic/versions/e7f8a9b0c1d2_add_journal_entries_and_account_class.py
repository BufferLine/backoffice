"""add journal_entries, journal_lines tables and account_class column

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-03-26 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'e7f8a9b0c1d2'
down_revision: Union[str, None] = 'd6e7f8a9b0c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add account_class to accounts
    op.add_column('accounts', sa.Column('account_class', sa.String(length=20), nullable=True))

    # Create journal_entries table
    op.create_table('journal_entries',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('entry_date', sa.Date(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('source_type', sa.String(length=30), nullable=True),
        sa.Column('source_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('is_confirmed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('confirmed_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('confirmed_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['confirmed_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create journal_lines table
    op.create_table('journal_lines',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('journal_entry_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('account_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('debit', sa.Numeric(precision=19, scale=6), nullable=False, server_default='0'),
        sa.Column('credit', sa.Numeric(precision=19, scale=6), nullable=False, server_default='0'),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('fx_rate_to_sgd', sa.Numeric(precision=19, scale=6), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['journal_entry_id'], ['journal_entries.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['currency'], ['currencies.code'], ondelete='RESTRICT'),
        sa.CheckConstraint(
            '(debit > 0 AND credit = 0) OR (debit = 0 AND credit > 0)',
            name='chk_debit_or_credit',
        ),
        sa.PrimaryKeyConstraint('id')
    )

    # Indexes for common queries
    op.create_index('ix_journal_entries_entry_date', 'journal_entries', ['entry_date'])
    op.create_index('ix_journal_entries_source', 'journal_entries', ['source_type', 'source_id'])
    op.create_index('ix_journal_lines_account_id', 'journal_lines', ['account_id'])
    op.create_index('ix_journal_lines_journal_entry_id', 'journal_lines', ['journal_entry_id'])

    # Enable RLS on new tables
    conn = op.get_bind()
    from sqlalchemy import text
    conn.execute(text('ALTER TABLE public."journal_entries" ENABLE ROW LEVEL SECURITY'))
    conn.execute(text('ALTER TABLE public."journal_lines" ENABLE ROW LEVEL SECURITY'))


def downgrade() -> None:
    op.drop_index('ix_journal_lines_journal_entry_id', table_name='journal_lines')
    op.drop_index('ix_journal_lines_account_id', table_name='journal_lines')
    op.drop_index('ix_journal_entries_source', table_name='journal_entries')
    op.drop_index('ix_journal_entries_entry_date', table_name='journal_entries')
    op.drop_table('journal_lines')
    op.drop_table('journal_entries')
    op.drop_column('accounts', 'account_class')
