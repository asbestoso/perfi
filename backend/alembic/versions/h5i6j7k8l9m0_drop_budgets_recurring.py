"""Drop budgets and recurring tables (feature removal)."""
from alembic import op
import sqlalchemy as sa

revision = "h5i6j7k8l9m0"
down_revision = "g3h4i5j6k7l8"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table("budgets")
    op.drop_table("recurring")


def downgrade():
    op.create_table(
        "recurring",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("cadence", sa.String(length=20), nullable=False),
        sa.Column("next_due", sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "budgets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("month", sa.String(length=7), nullable=False),
        sa.Column("limit_cents", sa.Integer(), nullable=False),
        sa.Column("rollover", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
