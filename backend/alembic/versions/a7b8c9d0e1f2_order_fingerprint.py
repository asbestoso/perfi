"""order idempotency fingerprint

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-09-16
"""

import sqlalchemy as sa
from alembic import op


revision = "a7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("investment_orders") as batch:
        batch.add_column(sa.Column("fingerprint", sa.String(length=32),
                                   nullable=True))
        batch.create_index("ix_investment_orders_fingerprint",
                           ["fingerprint"])


def downgrade():
    with op.batch_alter_table("investment_orders") as batch:
        batch.drop_index("ix_investment_orders_fingerprint")
        batch.drop_column("fingerprint")
