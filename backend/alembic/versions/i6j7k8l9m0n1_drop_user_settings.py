"""Drop user_settings table (AI settings feature removal)."""
from alembic import op

revision = "i6j7k8l9m0n1"
down_revision = "h5i6j7k8l9m0"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table("user_settings")


def downgrade():
    import sqlalchemy as sa
    op.create_table(
        "user_settings",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
