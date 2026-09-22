"""SQLAlchemy models. Money in INTEGER cents. Single-user (no auth tables)."""
import datetime as dt
from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import relationship

from .database import Base


class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True, nullable=False)
    name = Column(String(120), nullable=False, unique=True)
    type = Column(String(40), default="checking", nullable=False)
    domain = Column(String(20), default="spending", nullable=False)
    balance_cents = Column(Integer, default=0, nullable=False)


class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, nullable=False)
    name = Column(String(120), unique=True, nullable=False)
    parent = Column(String(120), nullable=True)
    transactions = relationship("Transaction", back_populates="category")
    rules = relationship("CategoryRule", back_populates="category")


class CategoryRule(Base):
    """User categorization rule: regex pattern -> category, lowest priority first."""
    __tablename__ = "category_rules"
    id = Column(Integer, primary_key=True, nullable=False)
    pattern = Column(String(200), nullable=False)
    category_id = Column(ForeignKey("categories.id"), nullable=False)
    priority = Column(Integer, default=0, nullable=False)
    category = relationship("Category", back_populates="rules")


class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, nullable=False)
    account_id = Column(ForeignKey("accounts.id"), nullable=False)
    category_id = Column(ForeignKey("categories.id"), nullable=True)
    amount_cents = Column(Integer, nullable=False)  # signed: +income, -spend
    merchant = Column(String(200), default="", nullable=False)
    date = Column(Date, nullable=False)
    note = Column(Text, nullable=True)
    transfer_id = Column(String(64), nullable=True)
    category_source = Column(String(20), nullable=True)
    transaction_kind = Column(String(32), default="expense", nullable=False)
    import_batch_id = Column(ForeignKey("import_batches.id"), nullable=True)
    fingerprint = Column(String(32), nullable=True, index=True)
    account = relationship("Account")
    category = relationship("Category", back_populates="transactions")


class Holding(Base):
    __tablename__ = "holdings"
    id = Column(Integer, primary_key=True, nullable=False)
    symbol = Column(String(20), nullable=False)
    name = Column(String(200), nullable=True)
    account_id = Column(ForeignKey("accounts.id"), nullable=True)
    quantity_milli = Column(Integer, default=0, nullable=False)  # qty * 1000
    price_cents = Column(Integer, default=0, nullable=False)
    import_batch_id = Column(ForeignKey("import_batches.id"), nullable=True)
    account = relationship("Account")
    __table_args__ = (
        Index("uq_holdings_account_symbol", "account_id", func.upper(symbol), unique=True),
    )


class InvestmentClassification(Base):
    __tablename__ = "investment_classifications"
    id = Column(Integer, primary_key=True, nullable=False)
    symbol = Column(String(20), nullable=False, unique=True)
    category = Column(String(20), nullable=False)


class InvestmentAllocation(Base):
    __tablename__ = "investment_allocations"
    id = Column(Integer, primary_key=True, nullable=False)
    symbol = Column(String(20), nullable=False)
    category = Column(String(20), nullable=False)
    percent_bps = Column(Integer, nullable=False)


class ImportBatch(Base):
    """One uploaded file: profile used, per-row outcomes in staging_rows.

    file_kind is mixed | brokerage | spending (user-confirmed intent);
    mapping is the confirmed canonical-field -> file-column JSON.
    """
    __tablename__ = "import_batches"
    id = Column(Integer, primary_key=True, nullable=False)
    profile = Column(String(20), default="empower", nullable=False)
    filename = Column(String(255), default="", nullable=False)
    account_id = Column(ForeignKey("accounts.id"), nullable=True)
    file_kind = Column(String(20), default="mixed", nullable=False)
    mapping = Column(Text, default="{}", nullable=False)
    status = Column(String(20), default="active", nullable=False)
    rolled_back_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    staged = Column(Integer, default=0, nullable=False)
    skipped = Column(Integer, default=0, nullable=False)
    account = relationship("Account")
    rows = relationship("StagingRow", back_populates="batch")


class ImportAccountMapping(Base):
    __tablename__ = "import_account_mappings"
    id = Column(Integer, primary_key=True, nullable=False)
    profile = Column(String(40), nullable=False)
    external_label = Column(String(255), nullable=False)
    account_id = Column(ForeignKey("accounts.id"), nullable=False)
    account = relationship("Account")
    __table_args__ = (
        UniqueConstraint("profile", "external_label"),
    )


class StagingRow(Base):
    """One parsed row awaiting user merge. Status: pending, merged, discarded, duplicate.

    row_kind is spend | brokerage_cash | unknown: where the row belongs.
    Unknown rows never merge into transactions; they wait for review on
    the Import page. transaction_kind presets the merged transaction's
    kind; row_detail holds a human reason for unknown rows.
    """
    __tablename__ = "staging_rows"
    id = Column(Integer, primary_key=True, nullable=False)
    batch_id = Column(ForeignKey("import_batches.id"), nullable=False)
    row_kind = Column(String(20), default="spend", nullable=False)
    transaction_kind = Column(String(32), default="expense", nullable=False)
    row_detail = Column(Text, default="", nullable=False)
    account_id = Column(ForeignKey("accounts.id"), nullable=True)
    date = Column(Date, nullable=False)
    merchant = Column(String(200), default="", nullable=False)
    amount_cents = Column(Integer, nullable=False)
    category_id = Column(ForeignKey("categories.id"), nullable=True)
    category_source = Column(String(20), nullable=True)
    note = Column(Text, nullable=True)
    status = Column(String(20), default="pending", nullable=False)
    raw = Column(Text, default="", nullable=False)
    batch = relationship("ImportBatch", back_populates="rows")
