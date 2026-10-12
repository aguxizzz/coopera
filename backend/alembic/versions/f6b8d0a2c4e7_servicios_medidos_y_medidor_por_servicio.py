"""servicios medidos por cooperativa y un medidor por servicio por socio

Revision ID: f6b8d0a2c4e7
Revises: e4a6c8f0b2d5
Create Date: 2026-10-12 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6b8d0a2c4e7'
down_revision: Union[str, Sequence[str], None] = 'e4a6c8f0b2d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Medidores que sobran: de cada socio y tipo se conserva el más viejo.
_EXTRA_METERS = """
    SELECT m.id FROM meters m
    WHERE m.id > (SELECT MIN(k.id) FROM meters k WHERE k.member_id = m.member_id AND k.tipo = m.tipo)
"""


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('tenants', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('servicios_medidos', sa.JSON(), nullable=False, server_default=sa.text("'[]'"))
        )

    # Un socio con dos medidores del mismo tipo choca con la regla nueva. Hoy
    # sólo existe la cooperativa demo, así que los que sobran se eliminan
    # junto con lo que cuelga de ellos.
    op.execute(f"UPDATE route_run_stops SET reading_id = NULL WHERE reading_id IN (SELECT id FROM readings WHERE meter_id IN ({_EXTRA_METERS}))")
    for table in ('route_run_stops', 'route_stops', 'service_cuts', 'readings'):
        op.execute(f"DELETE FROM {table} WHERE meter_id IN ({_EXTRA_METERS})")
    extra = [row[0] for row in op.get_bind().execute(sa.text(_EXTRA_METERS))]
    if extra:
        meters = sa.table('meters', sa.column('id', sa.Integer))
        op.execute(meters.delete().where(meters.c.id.in_(extra)))

    with op.batch_alter_table('meters', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_meter_member_tipo', ['member_id', 'tipo'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('meters', schema=None) as batch_op:
        batch_op.drop_constraint('uq_meter_member_tipo', type_='unique')

    with op.batch_alter_table('tenants', schema=None) as batch_op:
        batch_op.drop_column('servicios_medidos')
