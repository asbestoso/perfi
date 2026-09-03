from app import models
from app.services.categorization import categorize


def test_grocery_rule_case_insensitive():
    assert categorize("Whole Foods Market") == "Groceries"
    assert categorize("TRADER JOE'S #412") == "Groceries"


def test_dining_rule():
    assert categorize("STARBUCKS") == "Dining"


def test_income_rule():
    assert categorize("Payroll deposit ACME") == "Income"


def test_unknown_merchant_falls_through():
    assert categorize("Unknown Shop 123") == "Uncategorized"
    assert categorize("") == "Uncategorized"


def test_user_rule_beats_builtin_and_bad_regex_skipped():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.database import Base
    from app.services.categorization import resolve_category
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    db.add(models.Category(name="Groceries"))
    db.add(models.Category(name="Coffee"))
    db.commit()
    coffee = db.query(models.Category).filter_by(name="Coffee").one()
    db.add(models.CategoryRule(pattern="(broken", category_id=coffee.id, priority=0))
    db.add(models.CategoryRule(pattern="starbucks", category_id=coffee.id, priority=1))
    db.commit()
    assert resolve_category(db, "Starbucks Seattle") == ("Coffee", "rule")
    assert resolve_category(db, "Whole Foods") == ("Groceries", "rule")
    db.close()
