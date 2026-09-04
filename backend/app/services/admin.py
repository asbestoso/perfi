"""Destructive maintenance: wipe all user data, reseed defaults.

User settings (AI key etc.) are preserved — only domain data goes.
"""
from ..models import Account, BalanceSnapshot, Budget, Category, CategoryRule
from ..models import Holding, ImportBatch, InvestmentLot, Recurring
from ..models import SavedReport, StagingRow, Transaction

# Children before parents (SQLite does not enforce FKs here, but keep it safe).
WIPED = (StagingRow, Transaction, Budget, CategoryRule, ImportBatch,
         InvestmentLot, Holding, Recurring, BalanceSnapshot, SavedReport,
         Account, Category)


def clear_database(db):
    from ..seed import seed_categories
    deleted = {}
    for model in WIPED:
        deleted[model.__tablename__] = db.query(model).delete(
            synchronize_session=False)
    seed_categories(db)  # commits
    return deleted
