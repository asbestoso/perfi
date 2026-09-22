"""Destructive maintenance: wipe all user data, reseed defaults."""
from ..models import Account, Category, CategoryRule
from ..models import (Holding, ImportAccountMapping, ImportBatch,
                      InvestmentAllocation, InvestmentClassification)
from ..models import StagingRow, Transaction

# Children before parents (SQLite does not enforce FKs here, but keep it safe).
WIPED = (StagingRow, Transaction, CategoryRule, ImportAccountMapping,
         ImportBatch, InvestmentAllocation, InvestmentClassification,
         Holding, Account, Category)


def clear_database(db):
    from ..seed import seed_categories
    deleted = {}
    for model in WIPED:
        deleted[model.__tablename__] = db.query(model).delete(
            synchronize_session=False)
    seed_categories(db)  # commits
    return deleted
