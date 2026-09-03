"""SQLAlchemy models. Money in INTEGER cents. Single-user (no auth tables)."""
import datetime as dt
from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .database import Base


class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True, nullable=False)
    name = Column(String(120), nullable=False, unique=True)
    type = Column(String(40), default="checking", nullable=False)
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
    account = relationship("Account")
    category = relationship("Category", back_populates="transactions")


class Budget(Base):
    __tablename__ = "budgets"
    id = Column(Integer, primary_key=True, nullable=False)
    category_id = Column(ForeignKey("categories.id"), nullable=False)
    month = Column(String(7), nullable=False)  # YYYY-MM
    limit_cents = Column(Integer, nullable=False)
    rollover = Column(Boolean, default=False, nullable=False)


class Recurring(Base):
    __tablename__ = "recurring"
    id = Column(Integer, primary_key=True, nullable=False)
    name = Column(String(120), nullable=False)
    amount_cents = Column(Integer, nullable=False)
    cadence = Column(String(20), default="monthly", nullable=False)
    next_due = Column(Date, nullable=False)


class Holding(Base):
    __tablename__ = "holdings"
    id = Column(Integer, primary_key=True, nullable=False)
    symbol = Column(String(20), nullable=False)
    quantity_milli = Column(Integer, default=0, nullable=False)  # qty * 1000
    price_cents = Column(Integer, default=0, nullable=False)


class InvestmentLot(Base):
    """One tax lot: quantity and total cost basis. Market price comes from holdings."""
    __tablename__ = "investment_lots"
    id = Column(Integer, primary_key=True, nullable=False)
    symbol = Column(String(20), nullable=False)
    quantity_milli = Column(Integer, default=0, nullable=False)  # qty * 1000
    cost_cents = Column(Integer, default=0, nullable=False)  # total cost basis
    acquired = Column(Date, nullable=True)


class ImportBatch(Base):
    """One uploaded file: profile used, per-row outcomes in staging_rows."""
    __tablename__ = "import_batches"
    id = Column(Integer, primary_key=True, nullable=False)
    profile = Column(String(20), default="generic", nullable=False)
    filename = Column(String(255), default="", nullable=False)
    account_id = Column(ForeignKey("accounts.id"), nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    staged = Column(Integer, default=0, nullable=False)
    skipped = Column(Integer, default=0, nullable=False)
    account = relationship("Account")
    rows = relationship("StagingRow", back_populates="batch")


class BalanceSnapshot(Base):
    """One daily net-worth data point. Upserted by the snapshot job."""
    __tablename__ = "balance_snapshots"
    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False, unique=True)
    cash_cents = Column(Integer, nullable=False, default=0)
    investments_cents = Column(Integer, nullable=False, default=0)
    net_worth_cents = Column(Integer, nullable=False, default=0)


class UserSetting(Base):
    """Key-value settings. Secrets (AI key) stored Fernet-encrypted."""
    __tablename__ = "user_settings"
    key = Column(String(80), primary_key=True, nullable=False)
    value = Column(Text, nullable=False, default="")


class SavedReport(Base):
    """Named report with stored params. Types: spending, trends, net_worth, category_trends."""
    __tablename__ = "saved_reports"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    type = Column(String(40), nullable=False)
    params = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)


class StagingRow(Base):
    """One parsed row awaiting user merge. Status: pending, merged, discarded, duplicate."""
    __tablename__ = "staging_rows"
    id = Column(Integer, primary_key=True, nullable=False)
    batch_id = Column(ForeignKey("import_batches.id"), nullable=False)
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
