"""reading evidence photos (drop ocr, multi-foto)

Revision ID: b3c5d7e9f1a2
Revises: a2b4c6d8e0f1
Create Date: 2026-10-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3c5d7e9f1a2'
down_revision: Union[str, Sequence[str], None] = 'a2b4c6d8e0f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('readings', sa.Column('foto_urls', sa.JSON(), nullable=True))

    # Portable across sqlite/Postgres: carry over each reading's single
    # foto_url as a one-item list, row by row, instead of a dialect-specific
    # JSON-array SQL function.
    bind = op.get_bind()
    readings = sa.table(
        'readings',
        sa.column('id', sa.Integer()),
        sa.column('foto_url', sa.String()),
        sa.column('foto_urls', sa.JSON()),
    )
    rows = bind.execute(sa.select(readings.c.id, readings.c.foto_url).where(readings.c.foto_url.isnot(None)))
    for row in rows:
        bind.execute(
            readings.update().where(readings.c.id == row.id).values(foto_urls=[row.foto_url])
        )

    op.drop_column('readings', 'foto_url')
    op.drop_column('readings', 'ocr_valor')
    op.drop_column('readings', 'ocr_confianza')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('readings', sa.Column('foto_url', sa.String(length=500), nullable=True))
    op.add_column('readings', sa.Column('ocr_valor', sa.String(length=32), nullable=True))
    op.add_column('readings', sa.Column('ocr_confianza', sa.Float(), nullable=True))
    op.drop_column('readings', 'foto_urls')
