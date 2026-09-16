"""staging row kind details applied after f6 (dev DBs stamped f6 early)

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-09-16

Databases that migrated while f6 only carried row_kind need the three
columns f6 grew afterwards. Fresh databases get them from f6 directly;
the adds below are no-ops there only when columns already exist, so this
revision checks first and adds what is missing.
"""

import sqlalchemy as sa
from alembic import op


revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None

MISSING = [
    ("transaction_kind", sa.String(length=32), "expense"),
    ("row_detail", sa.Text(), ""),
    ("trade_json", sa.Text(), "{}"),
]


def upgrade():
    conn = op.get_bind()
    have = {r[1] for r in conn.exec_driver_sql("pragma table_info(staging_rows)")}
    with op.batch_alter_table("staging_rows") as batch:
        for name, type_, default in MISSING:
            if name not in have:
                batch.add_column(sa.Column(name, type_, nullable=False,
                                           server_default=default))


def downgrade():
    with op.batch_alter_table("staging_rows") as batch:
        batch.drop_column("trade_json")
        batch.drop_column("row_detail")
        batch.drop_column("transaction_kind")
