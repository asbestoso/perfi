"""support holdings CSV imports and persistent account mappings

Revision ID: e1f2a3b4c5d6
Revises: a9b8c7d6e5f4
Create Date: 2026-09-20
"""

import sqlalchemy as sa
from alembic import op


revision = "e1f2a3b4c5d6"
down_revision = "a9b8c7d6e5f4"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("holdings") as batch:
        batch.add_column(sa.Column("import_batch_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_holdings_import_batch", "import_batches",
                                 ["import_batch_id"], ["id"])
    op.create_table(
        "import_account_mappings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile", sa.String(length=40), nullable=False),
        sa.Column("external_label", sa.String(length=255), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("profile", "external_label"),
    )


def downgrade():
    op.drop_table("import_account_mappings")
    with op.batch_alter_table("holdings") as batch:
        batch.drop_constraint("fk_holdings_import_batch", type_="foreignkey")
        batch.drop_column("import_batch_id")
