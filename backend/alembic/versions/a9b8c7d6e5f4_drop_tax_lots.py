"""drop tax lots: orders and holdings only, no lot resolution

Revision ID: a9b8c7d6e5f4
Revises: c9d0e1f2a3b4
Create Date: 2026-09-16

InvestmentOrders keep the raw trade record (price, fees, proceeds);
holdings are the separate position ledger. Trade-analysis P&L is
computed on the fly, so no lot table or order cost/gain columns remain.
The pre-removal lots (15 rows) are kept only in the /tmp backup.
"""

import sqlalchemy as sa
from alembic import op


revision = "a9b8c7d6e5f4"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table("investment_lots")
    with op.batch_alter_table("investment_orders") as batch:
        batch.drop_column("cost_basis_cents")
        batch.drop_column("gain_cents")


def downgrade():
    with op.batch_alter_table("investment_orders") as batch:
        batch.add_column(sa.Column("cost_basis_cents", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("gain_cents", sa.Integer(), nullable=True))
    op.create_table(
        "investment_lots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("quantity_milli", sa.Integer(), nullable=False),
        sa.Column("cost_cents", sa.Integer(), nullable=False),
        sa.Column("acquired", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
