"""separate spending and investment domains

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-09-16
"""

import sqlalchemy as sa
from alembic import op


revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("accounts") as batch:
        batch.add_column(sa.Column("domain", sa.String(length=20),
                                   nullable=False, server_default="spending"))
    op.execute(
        "UPDATE accounts SET domain = 'investing' "
        "WHERE lower(type) IN ('brokerage', '401k', 'roth', "
        "'traditional ira', 'hsa', '529')"
    )
    with op.batch_alter_table("transactions") as batch:
        batch.add_column(sa.Column("transaction_kind", sa.String(length=32),
                                   nullable=False, server_default="expense"))


def downgrade():
    with op.batch_alter_table("transactions") as batch:
        batch.drop_column("transaction_kind")
    with op.batch_alter_table("accounts") as batch:
        batch.drop_column("domain")
