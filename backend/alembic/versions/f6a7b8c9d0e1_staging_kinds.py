"""stage row kinds + batch file kind and mapping

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-09-16
"""

import sqlalchemy as sa
from alembic import op


revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("import_batches") as batch:
        batch.add_column(sa.Column("file_kind", sa.String(length=20),
                                   nullable=False, server_default="mixed"))
        batch.add_column(sa.Column("mapping", sa.Text(),
                                   nullable=False, server_default="{}"))
    with op.batch_alter_table("staging_rows") as batch:
        batch.add_column(sa.Column("row_kind", sa.String(length=20),
                                   nullable=False, server_default="spend"))
        batch.add_column(sa.Column("transaction_kind", sa.String(length=32),
                                   nullable=False, server_default="expense"))
        batch.add_column(sa.Column("row_detail", sa.Text(),
                                   nullable=False, server_default=""))
        batch.add_column(sa.Column("trade_json", sa.Text(),
                                   nullable=False, server_default="{}"))


def downgrade():
    with op.batch_alter_table("staging_rows") as batch:
        batch.drop_column("trade_json")
        batch.drop_column("row_detail")
        batch.drop_column("transaction_kind")
        batch.drop_column("row_kind")
    with op.batch_alter_table("import_batches") as batch:
        batch.drop_column("mapping")
        batch.drop_column("file_kind")
