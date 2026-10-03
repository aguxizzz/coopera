"""gestor shared login

Revision ID: f1a2b3c4d5e6
Revises: d4e6a1f08b3c
Create Date: 2026-10-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'd4e6a1f08b3c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('tenants', schema=None) as batch_op:
        batch_op.add_column(sa.Column('gestor_shared_password_hash', sa.String(length=255), nullable=True))

    with op.batch_alter_table('gestores', schema=None) as batch_op:
        batch_op.drop_column('hashed_password')


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('gestores', schema=None) as batch_op:
        batch_op.add_column(sa.Column('hashed_password', sa.String(length=255), nullable=False, server_default=''))

    with op.batch_alter_table('tenants', schema=None) as batch_op:
        batch_op.drop_column('gestor_shared_password_hash')
