"""store investment categories by symbol

Revision ID: 9f6a2b3c4d5e
Revises: 8e5f9a2c1d4b
Create Date: 2026-09-11
"""

import sqlalchemy as sa
from alembic import op


revision = "9f6a2b3c4d5e"
down_revision = "8e5f9a2c1d4b"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "investment_classifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol"),
    )
    op.execute(
        "INSERT INTO investment_classifications (symbol, category) "
        "SELECT UPPER(symbol), MAX(category) FROM holdings "
        "WHERE category IS NOT NULL GROUP BY UPPER(symbol)"
    )
    with op.batch_alter_table("holdings") as batch:
        batch.drop_column("category")


def downgrade():
    with op.batch_alter_table("holdings") as batch:
        batch.add_column(sa.Column("category", sa.String(length=20), nullable=True))
    op.execute(
        "UPDATE holdings SET category = ("
        "SELECT category FROM investment_classifications "
        "WHERE investment_classifications.symbol = UPPER(holdings.symbol))"
    )
    op.drop_table("investment_classifications")
