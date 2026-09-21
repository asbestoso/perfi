"""Categorization tiers: user rules -> builtin rules -> merchant map -> Uncategorized.
"""
import re

RULES = [
    (r"whole\s*foods|trader\s*joe|kroger|safeway", "Groceries"),
    (r"starbucks|chipotle|mcdonald|restaurant|pizza", "Dining"),
    (r"uber|lyft|shell|chevron|delta|united", "Transport"),
    (r"landlord|rent|mortgage", "Housing"),
    (r"netflix|spotify|amc|cinema", "Entertainment"),
    (r"payroll|salary|deposit", "Income"),
]

MERCHANT_MAP = {}


def categorize(merchant):
    m = merchant.lower()
    for pattern, cat in RULES:
        if re.search(pattern, m):
            return cat
    return MERCHANT_MAP.get(m, "Uncategorized")


def resolve_category(db, merchant, rules=None):
    """Returns (category_name, source). Source is rule, merchant_default, or None."""
    from ..models import CategoryRule
    text = merchant or ""
    if rules is None:
        rules = db.query(CategoryRule).order_by(CategoryRule.priority).all()
    for r in rules:
        try:
            matched = re.search(r.pattern, text, re.IGNORECASE)
        except re.error:
            matched = False
        if matched:
            return r.category.name, "rule"
    name = categorize(text)
    if name != "Uncategorized":
        return name, "rule"
    hit = MERCHANT_MAP.get(text.lower())
    if hit is not None:
        return hit, "merchant_default"
    return "Uncategorized", None
