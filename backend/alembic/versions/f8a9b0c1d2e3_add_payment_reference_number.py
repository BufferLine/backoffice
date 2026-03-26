"""add payment reference_number with unique index

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-03-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f8a9b0c1d2e3'
down_revision: Union[str, None] = 'e7f8a9b0c1d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('payments', sa.Column('reference_number', sa.String(length=50), nullable=True))
    op.create_index(
        'uq_payments_reference_number_not_null',
        'payments',
        ['reference_number'],
        unique=True,
        postgresql_where=sa.text('reference_number IS NOT NULL'),
    )


def downgrade() -> None:
    op.drop_index('uq_payments_reference_number_not_null', table_name='payments')
    op.drop_column('payments', 'reference_number')
