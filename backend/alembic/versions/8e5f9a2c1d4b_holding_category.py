"""categorize investment holdings

Revision ID: 8e5f9a2c1d4b
Revises: 7d4e8a1c2b3f
Create Date: 2026-09-11
"""

import sqlalchemy as sa
from alembic import op


revision = "8e5f9a2c1d4b"
down_revision = "7d4e8a1c2b3f"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("holdings") as batch:
        batch.add_column(sa.Column("category", sa.String(length=20), nullable=True))


def downgrade():
    with op.batch_alter_table("holdings") as batch:
        batch.drop_column("category")
