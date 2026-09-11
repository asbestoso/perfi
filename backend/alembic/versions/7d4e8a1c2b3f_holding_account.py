"""associate holdings with accounts

Revision ID: 7d4e8a1c2b3f
Revises: f2a91c4e7b3d
Create Date: 2026-09-11
"""

import sqlalchemy as sa
from alembic import op


revision = "7d4e8a1c2b3f"
down_revision = "f2a91c4e7b3d"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("holdings") as batch:
        batch.add_column(sa.Column("account_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_holdings_account_id", "accounts", ["account_id"], ["id"]
        )


def downgrade():
    with op.batch_alter_table("holdings") as batch:
        batch.drop_constraint("fk_holdings_account_id", type_="foreignkey")
        batch.drop_column("account_id")
