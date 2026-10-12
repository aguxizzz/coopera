"""módulo portal de socios por cooperativa

Revision ID: d2f4a6c8e0b3
Revises: c9a1e3b5d7f2
Create Date: 2026-10-12 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd2f4a6c8e0b3'
down_revision: Union[str, Sequence[str], None] = 'c9a1e3b5d7f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('tenants', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('portal_socios_enabled', sa.Boolean(), nullable=False, server_default=sa.true())
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('tenants', schema=None) as batch_op:
        batch_op.drop_column('portal_socios_enabled')
