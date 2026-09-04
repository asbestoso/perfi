"""persisted transaction fingerprint (finance-app style identity)

Revision ID: f2a91c4e7b3d
Revises: 51171a03795c
Create Date: 2026-09-04

"""

import datetime as dt

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = 'f2a91c4e7b3d'
down_revision = '51171a03795c'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('transactions',
                  sa.Column('fingerprint', sa.String(length=32), nullable=True))
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT id, date, amount_cents, account_id, merchant FROM transactions")).all()
    if rows:
        # backend/ is on sys.path (see env.py); stdlib-only module, no cycles.
        from app.services.fingerprint import compute_fingerprint
        for rid, d, cents, aid, merchant in rows:
            day = dt.date.fromisoformat(d) if isinstance(d, str) else d
            fp = compute_fingerprint(day, cents, aid, merchant)
            conn.execute(sa.text("UPDATE transactions SET fingerprint = :fp WHERE id = :id"),
                         {"fp": fp, "id": rid})
    op.create_index('ix_transactions_fingerprint', 'transactions', ['fingerprint'])


def downgrade():
    op.drop_index('ix_transactions_fingerprint', table_name='transactions')
    op.drop_column('transactions', 'fingerprint')
