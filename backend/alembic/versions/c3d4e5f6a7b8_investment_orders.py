"""add investment orders and account-linked lots

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-09-15
"""

import sqlalchemy as sa
from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("investment_lots") as batch:
        batch.add_column(sa.Column("account_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_investment_lots_account_id", "accounts", ["account_id"], ["id"])
    op.create_table(
        "investment_orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("side", sa.String(length=4), nullable=False),
        sa.Column("quantity_milli", sa.Integer(), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("fees_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("executed_at", sa.Date(), nullable=False),
        sa.Column("proceeds_cents", sa.Integer(), nullable=True),
        sa.Column("cost_basis_cents", sa.Integer(), nullable=True),
        sa.Column("gain_cents", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("investment_orders")
    with op.batch_alter_table("investment_lots") as batch:
        batch.drop_constraint("fk_investment_lots_account_id", type_="foreignkey")
        batch.drop_column("account_id")
