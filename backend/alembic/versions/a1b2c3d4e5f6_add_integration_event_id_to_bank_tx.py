"""add integration_event_id to bank_transactions

Revision ID: a1b2c3d4e5f6
Revises: 937c7c494521
Create Date: 2026-03-21 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '937c7c494521'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'bank_transactions',
        sa.Column('integration_event_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'fk_bank_transactions_integration_event_id',
        'bank_transactions',
        'integration_events',
        ['integration_event_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_bank_transactions_integration_event_id', 'bank_transactions', type_='foreignkey')
    op.drop_column('bank_transactions', 'integration_event_id')
