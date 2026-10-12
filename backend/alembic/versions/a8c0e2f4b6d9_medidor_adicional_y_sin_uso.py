"""medidor adicional del mismo servicio y aviso de servicio sin uso

Revision ID: a8c0e2f4b6d9
Revises: f6b8d0a2c4e7
Create Date: 2026-10-12 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a8c0e2f4b6d9'
down_revision: Union[str, Sequence[str], None] = 'f6b8d0a2c4e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('meters', schema=None) as batch_op:
        batch_op.add_column(sa.Column('adicional', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('sin_uso_reportado_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('sin_uso_reportado_por_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_meters_sin_uso_reportado_por', 'gestores', ['sin_uso_reportado_por_id'], ['id']
        )
        batch_op.drop_constraint('uq_meter_member_tipo', type_='unique')

    # La unicidad socio + servicio pasa a valer sólo para el medidor
    # principal: los marcados `adicional` quedan afuera.
    op.create_index(
        'uq_meter_member_tipo_principal',
        'meters',
        ['member_id', 'tipo'],
        unique=True,
        sqlite_where=sa.text('NOT adicional'),
        postgresql_where=sa.text('NOT adicional'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_meter_member_tipo_principal', table_name='meters')

    # Sin la excepción, los adicionales chocan con la unicidad: se desactivan
    # a mano antes de bajar; acá sólo se restituye la regla.
    with op.batch_alter_table('meters', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_meter_member_tipo', ['member_id', 'tipo'])
        batch_op.drop_constraint('fk_meters_sin_uso_reportado_por', type_='foreignkey')
        batch_op.drop_column('sin_uso_reportado_por_id')
        batch_op.drop_column('sin_uso_reportado_at')
        batch_op.drop_column('adicional')
