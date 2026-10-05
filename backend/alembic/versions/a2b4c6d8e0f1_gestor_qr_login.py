"""gestor qr login

Revision ID: a2b4c6d8e0f1
Revises: e5f7a2c9d1b4
Create Date: 2026-10-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a2b4c6d8e0f1'
down_revision: Union[str, Sequence[str], None] = 'e5f7a2c9d1b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'gestor_qr_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('device_token', sa.String(length=1000), nullable=True),
        sa.Column('consumed', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_gestor_qr_sessions_tenant_id'), 'gestor_qr_sessions', ['tenant_id'], unique=False
    )
    op.create_index(
        op.f('ix_gestor_qr_sessions_code'), 'gestor_qr_sessions', ['code'], unique=True
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_gestor_qr_sessions_code'), table_name='gestor_qr_sessions')
    op.drop_index(op.f('ix_gestor_qr_sessions_tenant_id'), table_name='gestor_qr_sessions')
    op.drop_table('gestor_qr_sessions')
