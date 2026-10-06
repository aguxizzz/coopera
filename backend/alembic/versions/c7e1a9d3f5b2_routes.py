"""rutas de lectura y recorridos

Revision ID: c7e1a9d3f5b2
Revises: b3c5d7e9f1a2
Create Date: 2026-10-06 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7e1a9d3f5b2'
down_revision: Union[str, Sequence[str], None] = 'b3c5d7e9f1a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'routes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('nombre', sa.String(length=120), nullable=False),
        sa.Column('gestor_id', sa.Integer(), nullable=True),
        sa.Column('origen', sa.String(length=16), nullable=False, server_default='manual'),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['gestor_id'], ['gestores.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_routes_tenant_id', 'routes', ['tenant_id'])

    op.create_table(
        'route_stops',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('route_id', sa.Integer(), nullable=False),
        sa.Column('meter_id', sa.Integer(), nullable=False),
        sa.Column('orden', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['route_id'], ['routes.id']),
        sa.ForeignKeyConstraint(['meter_id'], ['meters.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('route_id', 'meter_id', name='uq_route_stop_meter'),
    )
    op.create_index('ix_route_stops_route_id', 'route_stops', ['route_id'])

    op.create_table(
        'route_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('route_id', sa.Integer(), nullable=False),
        sa.Column('gestor_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='en_curso'),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['route_id'], ['routes.id']),
        sa.ForeignKeyConstraint(['gestor_id'], ['gestores.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_route_runs_tenant_id', 'route_runs', ['tenant_id'])

    op.create_table(
        'route_run_stops',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.Integer(), nullable=False),
        sa.Column('meter_id', sa.Integer(), nullable=False),
        sa.Column('orden', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='pendiente'),
        sa.Column('motivo', sa.String(length=255), nullable=True),
        sa.Column('reading_id', sa.Integer(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['run_id'], ['route_runs.id']),
        sa.ForeignKeyConstraint(['meter_id'], ['meters.id']),
        sa.ForeignKeyConstraint(['reading_id'], ['readings.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_route_run_stops_run_id', 'route_run_stops', ['run_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_route_run_stops_run_id', table_name='route_run_stops')
    op.drop_table('route_run_stops')
    op.drop_index('ix_route_runs_tenant_id', table_name='route_runs')
    op.drop_table('route_runs')
    op.drop_index('ix_route_stops_route_id', table_name='route_stops')
    op.drop_table('route_stops')
    op.drop_index('ix_routes_tenant_id', table_name='routes')
    op.drop_table('routes')
