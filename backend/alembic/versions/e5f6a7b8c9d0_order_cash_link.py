"""link investment orders to their cash transaction

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-16
"""

import sqlalchemy as sa
from alembic import op


revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("investment_orders") as batch:
        batch.add_column(sa.Column("linked_transaction_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_investment_orders_linked_transaction_id",
                                 "transactions", ["linked_transaction_id"], ["id"])


def downgrade():
    with op.batch_alter_table("investment_orders") as batch:
        batch.drop_constraint("fk_investment_orders_linked_transaction_id", type_="foreignkey")
        batch.drop_column("linked_transaction_id")
