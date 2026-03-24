"""add agreement, statement, discharge file IDs to loans

Revision ID: c5d6e7f8a9b0
Revises: b3c4d5e6f7a8
Create Date: 2026-03-24 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'c5d6e7f8a9b0'
down_revision: Union[str, None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('loans', sa.Column(
        'agreement_file_id', postgresql.UUID(as_uuid=True), nullable=True,
    ))
    op.add_column('loans', sa.Column(
        'latest_statement_file_id', postgresql.UUID(as_uuid=True), nullable=True,
    ))
    op.add_column('loans', sa.Column(
        'discharge_file_id', postgresql.UUID(as_uuid=True), nullable=True,
    ))
    op.create_foreign_key(
        'fk_loans_agreement_file_id', 'loans', 'files',
        ['agreement_file_id'], ['id'], ondelete='SET NULL',
    )
    op.create_foreign_key(
        'fk_loans_latest_statement_file_id', 'loans', 'files',
        ['latest_statement_file_id'], ['id'], ondelete='SET NULL',
    )
    op.create_foreign_key(
        'fk_loans_discharge_file_id', 'loans', 'files',
        ['discharge_file_id'], ['id'], ondelete='SET NULL',
    )

    # Migrate existing document_file_id → agreement_file_id
    op.execute(sa.text("""
        UPDATE loans
        SET agreement_file_id = document_file_id
        WHERE document_file_id IS NOT NULL
    """))


def downgrade() -> None:
    op.drop_constraint('fk_loans_discharge_file_id', 'loans', type_='foreignkey')
    op.drop_constraint('fk_loans_latest_statement_file_id', 'loans', type_='foreignkey')
    op.drop_constraint('fk_loans_agreement_file_id', 'loans', type_='foreignkey')
    op.drop_column('loans', 'discharge_file_id')
    op.drop_column('loans', 'latest_statement_file_id')
    op.drop_column('loans', 'agreement_file_id')
