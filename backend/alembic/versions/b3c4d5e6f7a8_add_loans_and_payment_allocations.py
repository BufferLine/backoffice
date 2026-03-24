"""add loans and payment_allocations tables

Revision ID: b3c4d5e6f7a8
Revises: a1b2c3d4e5f6
Create Date: 2026-03-24 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'loans',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('loan_type', sa.String(30), nullable=False),
        sa.Column('direction', sa.String(10), nullable=False),
        sa.Column('counterparty', sa.String(255), nullable=False),
        sa.Column('currency', sa.String(10), sa.ForeignKey('currencies.code', ondelete='RESTRICT'), nullable=False),
        sa.Column('principal', sa.Numeric(19, 6), nullable=False),
        sa.Column('interest_rate', sa.Numeric(8, 6), nullable=False, server_default='0'),
        sa.Column('interest_type', sa.String(20), nullable=False, server_default='simple'),
        sa.Column('start_date', sa.Date, nullable=False),
        sa.Column('maturity_date', sa.Date, nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='active'),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('document_file_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('files.id', ondelete='SET NULL'), nullable=True),
        sa.Column('metadata_json', postgresql.JSONB, nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        'payment_allocations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('payment_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('payments.id', ondelete='CASCADE'), nullable=False),
        sa.Column('entity_type', sa.String(30), nullable=False),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('amount', sa.Numeric(19, 6), nullable=False),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_index('ix_payment_allocations_payment_id', 'payment_allocations', ['payment_id'])
    op.create_index('ix_payment_allocations_entity', 'payment_allocations', ['entity_type', 'entity_id'])

    # Data migration: convert existing Payment.related_entity_type/id → PaymentAllocation rows.
    # This preserves backward compatibility while enabling the new allocation system.
    op.execute(sa.text("""
        INSERT INTO payment_allocations (id, payment_id, entity_type, entity_id, amount, created_by, created_at)
        SELECT gen_random_uuid(), id, related_entity_type, related_entity_id, amount, created_by, created_at
        FROM payments
        WHERE related_entity_type IS NOT NULL
          AND related_entity_id IS NOT NULL
    """))


def downgrade() -> None:
    op.drop_index('ix_payment_allocations_entity', 'payment_allocations')
    op.drop_index('ix_payment_allocations_payment_id', 'payment_allocations')
    op.drop_table('payment_allocations')
    op.drop_table('loans')
