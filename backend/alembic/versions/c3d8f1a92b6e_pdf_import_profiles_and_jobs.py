"""pdf import profiles and jobs

Revision ID: c3d8f1a92b6e
Revises: 9867beb758c4
Create Date: 2026-10-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d8f1a92b6e'
down_revision: Union[str, Sequence[str], None] = '9867beb758c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'pdf_import_profiles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('field_patterns', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id'),
    )

    op.create_table(
        'pdf_import_jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('period_year', sa.Integer(), nullable=False),
        sa.Column('period_month', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='pending'),
        sa.Column('total_pages', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('processed_pages', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error', sa.String(length=1000), nullable=True),
        sa.Column('import_batch_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['import_batch_id'], ['import_batches.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('pdf_import_jobs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_pdf_import_jobs_tenant_id'), ['tenant_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('pdf_import_jobs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_pdf_import_jobs_tenant_id'))
    op.drop_table('pdf_import_jobs')
    op.drop_table('pdf_import_profiles')
