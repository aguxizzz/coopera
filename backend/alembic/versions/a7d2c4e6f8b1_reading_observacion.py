"""observación del gestor en la lectura

Revision ID: a7d2c4e6f8b1
Revises: c7e1a9d3f5b2
Create Date: 2026-10-07 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7d2c4e6f8b1'
down_revision: Union[str, Sequence[str], None] = 'c7e1a9d3f5b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('readings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('observacion', sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('readings', schema=None) as batch_op:
        batch_op.drop_column('observacion')
