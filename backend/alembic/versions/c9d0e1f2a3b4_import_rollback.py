"""track records created by import batches for rollback

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-09-16
"""

import sqlalchemy as sa
from alembic import op


revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("transactions") as batch:
        batch.add_column(sa.Column("import_batch_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_transactions_import_batch", "import_batches",
                                 ["import_batch_id"], ["id"])
    with op.batch_alter_table("investment_orders") as batch:
        batch.add_column(sa.Column("import_batch_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_orders_import_batch", "import_batches",
                                 ["import_batch_id"], ["id"])
    with op.batch_alter_table("import_batches") as batch:
        batch.add_column(sa.Column("status", sa.String(length=20),
                                   nullable=False, server_default="active"))
        batch.add_column(sa.Column("rolled_back_at", sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table("import_batches") as batch:
        batch.drop_column("rolled_back_at")
        batch.drop_column("status")
    with op.batch_alter_table("investment_orders") as batch:
        batch.drop_constraint("fk_orders_import_batch", type_="foreignkey")
        batch.drop_column("import_batch_id")
    with op.batch_alter_table("transactions") as batch:
        batch.drop_constraint("fk_transactions_import_batch", type_="foreignkey")
        batch.drop_column("import_batch_id")
