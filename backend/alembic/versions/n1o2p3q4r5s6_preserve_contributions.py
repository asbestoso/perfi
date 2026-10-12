"""Preserve investment cash flows when accounts are deleted."""
from alembic import op
import sqlalchemy as sa

revision = "n1o2p3q4r5s6"
down_revision = "m0n1o2p3q4r5"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("investment_contributions") as batch:
        batch.alter_column("account_id", existing_type=sa.Integer(), nullable=True)


def downgrade():
    with op.batch_alter_table("investment_contributions") as batch:
        batch.alter_column("account_id", existing_type=sa.Integer(), nullable=False)
