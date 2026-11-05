"""payments.onchain_verification: stored result of on-chain receipt verification

Revision ID: 7d2e8b41c9f3
Revises: 4a7c91e2d5b6
Create Date: 2026-11-05 18:00:00.000000

Holds the JSON result of verifying a stablecoin receipt against the chain
(token contract, recipient, amount, confirmations, block time), or the reason
verification was skipped. NULL for payments recorded without verification.

Also adds a unique index on lower(tx_hash) so case variants of one EVM hash
cannot be recorded twice (fails loudly if existing rows already collide).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '7d2e8b41c9f3'
down_revision: Union[str, None] = '4a7c91e2d5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('payments', sa.Column('onchain_verification', postgresql.JSONB(), nullable=True))

    # Case-insensitive tx_hash uniqueness (0xABC.. == 0xabc.. for EVM chains).
    bind = op.get_bind()
    dupes = bind.execute(sa.text(
        "SELECT lower(tx_hash) FROM payments WHERE tx_hash IS NOT NULL "
        "GROUP BY lower(tx_hash) HAVING COUNT(*) > 1"
    )).fetchall()
    if dupes:
        raise RuntimeError(
            "Payments share a tx_hash that differs only by case; resolve before upgrading: "
            + ", ".join(r[0] for r in dupes)
        )
    op.create_index(
        'uq_payments_tx_hash_lower', 'payments', [sa.text('lower(tx_hash)')],
        unique=True, postgresql_where=sa.text('tx_hash IS NOT NULL'),
    )


def downgrade() -> None:
    op.drop_index('uq_payments_tx_hash_lower', table_name='payments')
    op.drop_column('payments', 'onchain_verification')
