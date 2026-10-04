"""add macroclick (banco macro, no oficial) fields to tenants

Revision ID: e5f7a2c9d1b4
Revises: b7c4e92a1f05
Create Date: 2026-10-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f7a2c9d1b4'
down_revision: Union[str, Sequence[str], None] = 'b7c4e92a1f05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('tenants', sa.Column('macroclick_comercio_id', sa.String(length=64), nullable=True))
    op.add_column('tenants', sa.Column('macroclick_sucursal', sa.String(length=32), nullable=True))
    op.add_column('tenants', sa.Column('macroclick_secret_key', sa.String(length=1000), nullable=True))
    op.add_column(
        'tenants',
        sa.Column('macroclick_environment', sa.String(length=16), server_default='sandbox', nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('tenants', 'macroclick_environment')
    op.drop_column('tenants', 'macroclick_secret_key')
    op.drop_column('tenants', 'macroclick_sucursal')
    op.drop_column('tenants', 'macroclick_comercio_id')
