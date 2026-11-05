"""autonomy level on drafts and jobs, default 1 (a person approves)

Revision ID: b2d4f6a8c0e1
Revises: a1c3e5f7b9d0
Create Date: 2026-11-05 17:21:00
"""
import sqlalchemy as sa
from alembic import op

revision = 'b2d4f6a8c0e1'
down_revision = 'a1c3e5f7b9d0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ('drafts', 'jobs'):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column('autonomy_level', sa.Integer(), server_default='1', nullable=False))
    # drafts that automatic send already sent were level 2
    op.execute("UPDATE drafts SET autonomy_level = 2 WHERE decided_by LIKE 'auto:%'")


def downgrade() -> None:
    for table in ('drafts', 'jobs'):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_column('autonomy_level')
