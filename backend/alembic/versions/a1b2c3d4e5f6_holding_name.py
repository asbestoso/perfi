"""store security names for holdings

Revision ID: a1b2c3d4e5f6
Revises: 9f6a2b3c4d5e
Create Date: 2026-09-11
"""

import sqlalchemy as sa
from alembic import op


revision = "a1b2c3d4e5f6"
down_revision = "9f6a2b3c4d5e"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("holdings") as batch:
        batch.add_column(sa.Column("name", sa.String(length=200), nullable=True))


def downgrade():
    with op.batch_alter_table("holdings") as batch:
        batch.drop_column("name")
