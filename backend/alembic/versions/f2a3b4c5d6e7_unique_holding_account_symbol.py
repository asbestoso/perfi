"""enforce one holding per account and symbol"""

import sqlalchemy as sa
from alembic import op


revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "uq_holdings_account_symbol",
        "holdings",
        ["account_id", sa.text("upper(symbol)")],
        unique=True,
    )


def downgrade():
    op.drop_index("uq_holdings_account_symbol", table_name="holdings")
