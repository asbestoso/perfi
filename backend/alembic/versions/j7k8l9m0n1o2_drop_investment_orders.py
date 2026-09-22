"""Drop investment orders table and staging trade payload (trades removed)."""
from alembic import op
import sqlalchemy as sa

revision = "j7k8l9m0n1o2"
down_revision = "i6j7k8l9m0n1"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table("investment_orders")
    with op.batch_alter_table("staging_rows") as batch:
        batch.drop_column("trade_json")


def downgrade():
    op.create_table(
        "investment_orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("linked_transaction_id", sa.Integer(), nullable=True),
        sa.Column("fingerprint", sa.String(length=32), nullable=True),
        sa.Column("import_batch_id", sa.Integer(), nullable=True),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("side", sa.String(length=4), nullable=False),
        sa.Column("quantity_milli", sa.Integer(), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("fees_cents", sa.Integer(), nullable=False),
        sa.Column("executed_at", sa.Date(), nullable=False),
        sa.Column("proceeds_cents", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["import_batch_id"], ["import_batches.id"]),
        sa.ForeignKeyConstraint(["linked_transaction_id"], ["transactions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("staging_rows") as batch:
        batch.add_column(sa.Column("trade_json", sa.Text(), server_default="{}"))
