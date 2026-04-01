"""add fx_conversions table

Revision ID: a1b2c3d4e5f6
Revises: f8a9b0c1d2e3
Create Date: 2026-04-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f8a9b0c1d2e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'fx_conversions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('conversion_date', sa.Date(), nullable=False),
        sa.Column('sell_currency', sa.String(10), sa.ForeignKey('currencies.code', ondelete='RESTRICT'), nullable=False),
        sa.Column('sell_amount', sa.Numeric(19, 6), nullable=False),
        sa.Column('buy_currency', sa.String(10), sa.ForeignKey('currencies.code', ondelete='RESTRICT'), nullable=False),
        sa.Column('buy_amount', sa.Numeric(19, 6), nullable=False),
        sa.Column('fx_rate', sa.Numeric(19, 10), nullable=False),
        sa.Column('sell_account_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('accounts.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('buy_account_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('accounts.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('journal_entry_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('journal_entries.id', ondelete='SET NULL'), nullable=True),
        sa.Column('provider', sa.String(100), nullable=True),
        sa.Column('reference', sa.String(255), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_fx_conversions_date', 'fx_conversions', ['conversion_date'])
    op.create_index('ix_fx_conversions_sell_currency', 'fx_conversions', ['sell_currency'])
    op.create_index('ix_fx_conversions_buy_currency', 'fx_conversions', ['buy_currency'])


def downgrade() -> None:
    op.drop_index('ix_fx_conversions_buy_currency', table_name='fx_conversions')
    op.drop_index('ix_fx_conversions_sell_currency', table_name='fx_conversions')
    op.drop_index('ix_fx_conversions_date', table_name='fx_conversions')
    op.drop_table('fx_conversions')
