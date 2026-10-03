"""gestor refresh token

Revision ID: d4e6a1f08b3c
Revises: c3d8f1a92b6e
Create Date: 2026-10-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e6a1f08b3c'
down_revision: Union[str, Sequence[str], None] = 'c3d8f1a92b6e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('gestores', schema=None) as batch_op:
        batch_op.add_column(sa.Column('refresh_token_hash', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('refresh_token_expires_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('gestores', schema=None) as batch_op:
        batch_op.drop_column('refresh_token_expires_at')
        batch_op.drop_column('refresh_token_hash')
