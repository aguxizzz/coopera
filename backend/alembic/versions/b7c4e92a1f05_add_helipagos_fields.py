"""add helipagos fields to tenants and invoices

Revision ID: b7c4e92a1f05
Revises: f1a2b3c4d5e6
Create Date: 2026-10-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c4e92a1f05'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('tenants', sa.Column('helipagos_token', sa.String(length=1000), nullable=True))
    op.add_column('tenants', sa.Column('helipagos_webhook_apikey', sa.String(length=500), nullable=True))
    op.add_column(
        'tenants',
        sa.Column('helipagos_environment', sa.String(length=16), server_default='sandbox', nullable=False),
    )
    op.add_column('invoices', sa.Column('helipagos_id_sp', sa.String(length=64), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('invoices', 'helipagos_id_sp')
    op.drop_column('tenants', 'helipagos_environment')
    op.drop_column('tenants', 'helipagos_webhook_apikey')
    op.drop_column('tenants', 'helipagos_token')
