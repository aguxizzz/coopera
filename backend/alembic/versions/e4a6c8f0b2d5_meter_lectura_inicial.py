"""lectura inicial del medidor

Revision ID: e4a6c8f0b2d5
Revises: d2f4a6c8e0b3
Create Date: 2026-10-12 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4a6c8f0b2d5'
down_revision: Union[str, Sequence[str], None] = 'd2f4a6c8e0b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('meters', schema=None) as batch_op:
        batch_op.add_column(sa.Column('lectura_inicial', sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('meters', schema=None) as batch_op:
        batch_op.drop_column('lectura_inicial')
