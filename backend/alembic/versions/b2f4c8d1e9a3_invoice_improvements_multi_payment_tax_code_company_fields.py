"""invoice improvements: multi payment method, per-line tax code, company gst/website fields

Revision ID: b2f4c8d1e9a3
Revises: 438bbed36d57
Create Date: 2026-03-20 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b2f4c8d1e9a3'
down_revision: Union[str, None] = '438bbed36d57'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── invoice_payment_methods join table ───────────────────────────────────
    op.create_table(
        'invoice_payment_methods',
        sa.Column('invoice_id', sa.UUID(), nullable=False),
        sa.Column('payment_method_id', sa.UUID(), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=True, server_default='0'),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['payment_method_id'], ['payment_methods.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('invoice_id', 'payment_method_id'),
    )

    # ── per-line-item tax fields on invoice_line_items ───────────────────────
    op.add_column(
        'invoice_line_items',
        sa.Column('tax_code', sa.String(length=10), nullable=False, server_default='SR'),
    )
    op.add_column(
        'invoice_line_items',
        sa.Column('tax_rate', sa.Numeric(5, 4), nullable=True),
    )
    op.add_column(
        'invoice_line_items',
        sa.Column('tax_amount', sa.Numeric(19, 6), nullable=False, server_default='0'),
    )

    # ── company_settings additions ───────────────────────────────────────────
    op.add_column(
        'company_settings',
        sa.Column('gst_registration_number', sa.String(length=50), nullable=True),
    )
    op.add_column(
        'company_settings',
        sa.Column('website', sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    # company_settings
    op.drop_column('company_settings', 'website')
    op.drop_column('company_settings', 'gst_registration_number')

    # invoice_line_items
    op.drop_column('invoice_line_items', 'tax_amount')
    op.drop_column('invoice_line_items', 'tax_rate')
    op.drop_column('invoice_line_items', 'tax_code')

    # invoice_payment_methods join table
    op.drop_table('invoice_payment_methods')
