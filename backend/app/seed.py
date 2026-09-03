"""Seed default categories (idempotent)."""
from sqlalchemy import select

from .models import Category

DEFAULT_CATEGORIES = [
    ("Groceries", None), ("Dining", None), ("Transport", None),
    ("Housing", None), ("Utilities", None), ("Health", None),
    ("Entertainment", None), ("Shopping", None), ("Income", None),
    ("Transfer", None), ("Uncategorized", None),
]


def seed_categories(db):
    existing = {c.name for c in db.scalars(select(Category)).all()}
    for name, parent in DEFAULT_CATEGORIES:
        if name not in existing:
            db.add(Category(name=name, parent=parent))
    db.commit()
