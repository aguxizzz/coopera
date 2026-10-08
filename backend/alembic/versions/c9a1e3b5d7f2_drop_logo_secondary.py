"""quitar logo secundario

Revision ID: c9a1e3b5d7f2
Revises: b8e3d5f7a9c1
Create Date: 2026-10-08 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9a1e3b5d7f2'
down_revision: Union[str, Sequence[str], None] = 'b8e3d5f7a9c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('tenants') as batch_op:
        batch_op.drop_column('logo_secondary_url')


def downgrade() -> None:
    with op.batch_alter_table('tenants') as batch_op:
        batch_op.add_column(sa.Column('logo_secondary_url', sa.String(length=500), nullable=True))
