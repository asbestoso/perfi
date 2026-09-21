"""drop reports tables: saved_reports and balance_snapshots

Revision ID: g3h4i5j6k7l8
Revises: f2a3b4c5d6e7
Create Date: 2026-09-21

Reports (month view, trends, category trends), net-worth snapshots, and
saved reports are removed. The underlying transactions, budgets, accounts,
and holdings stay; only the snapshot series and saved-report storage go.
"""

import sqlalchemy as sa
from alembic import op


revision = "g3h4i5j6k7l8"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table("saved_reports")
    op.drop_table("balance_snapshots")


def downgrade():
    op.create_table(
        "balance_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("cash_cents", sa.Integer(), nullable=False),
        sa.Column("investments_cents", sa.Integer(), nullable=False),
        sa.Column("net_worth_cents", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("date"),
    )
    op.create_table(
        "saved_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("type", sa.String(length=40), nullable=False),
        sa.Column("params", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
