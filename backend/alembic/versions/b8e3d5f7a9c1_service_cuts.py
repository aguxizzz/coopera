"""cortes de servicio

Revision ID: b8e3d5f7a9c1
Revises: a7d2c4e6f8b1
Create Date: 2026-10-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8e3d5f7a9c1'
down_revision: Union[str, Sequence[str], None] = 'a7d2c4e6f8b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'service_cuts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('member_id', sa.Integer(), nullable=False),
        sa.Column('meter_id', sa.Integer(), nullable=False),
        sa.Column('motivo', sa.String(length=16), nullable=False),
        sa.Column('detalle', sa.String(length=500), nullable=True),
        sa.Column('estado', sa.String(length=24), nullable=False),
        sa.Column('ordenado_por_email', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('ejecutado_por_id', sa.Integer(), nullable=True),
        sa.Column('ejecutado_at', sa.DateTime(), nullable=True),
        sa.Column('ejecucion_nota', sa.String(length=500), nullable=True),
        sa.Column('ejecucion_foto_urls', sa.JSON(), nullable=True),
        sa.Column('ejecucion_lat', sa.Float(), nullable=True),
        sa.Column('ejecucion_lon', sa.Float(), nullable=True),
        sa.Column('reposicion_ordenada_por_email', sa.String(length=255), nullable=True),
        sa.Column('reposicion_ordenada_at', sa.DateTime(), nullable=True),
        sa.Column('repuesto_por_id', sa.Integer(), nullable=True),
        sa.Column('repuesto_at', sa.DateTime(), nullable=True),
        sa.Column('reposicion_nota', sa.String(length=500), nullable=True),
        sa.Column('reposicion_foto_urls', sa.JSON(), nullable=True),
        sa.Column('reposicion_lat', sa.Float(), nullable=True),
        sa.Column('reposicion_lon', sa.Float(), nullable=True),
        sa.Column('cancelado_por_email', sa.String(length=255), nullable=True),
        sa.Column('cancelado_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['member_id'], ['members.id']),
        sa.ForeignKeyConstraint(['meter_id'], ['meters.id']),
        sa.ForeignKeyConstraint(['ejecutado_por_id'], ['gestores.id']),
        sa.ForeignKeyConstraint(['repuesto_por_id'], ['gestores.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('service_cuts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_service_cuts_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_service_cuts_member_id'), ['member_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_service_cuts_meter_id'), ['meter_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_service_cuts_estado'), ['estado'], unique=False)
        batch_op.create_index(batch_op.f('ix_service_cuts_created_at'), ['created_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('service_cuts')
