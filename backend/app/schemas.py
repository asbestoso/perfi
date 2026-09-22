"""Pydantic schemas: Read/Create/Update split."""
import datetime as dt

from typing import Generic, Optional, TypeVar
from pydantic import BaseModel, ConfigDict, field_validator

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int


class AccountCreate(BaseModel):
    name: str
    type: str = "checking"
    domain: str = "spending"
    balance_cents: int = 0


class AccountRead(AccountCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    domain: Optional[str] = None


class CategoryCreate(BaseModel):
    name: str
    parent: Optional[str] = None


class CategoryRead(CategoryCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)


class TransactionCreate(BaseModel):
    account_id: Optional[int] = None
    category_id: Optional[int] = None
    amount_cents: int
    merchant: str = ""
    date: dt.date
    note: Optional[str] = None
    transfer_id: Optional[str] = None
    transaction_kind: str = "expense"


class TransactionRead(TransactionCreate):
    id: int
    category_source: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class TransactionUpdate(BaseModel):
    merchant: Optional[str] = None
    note: Optional[str] = None
    date: Optional[dt.date] = None
    account_id: Optional[int] = None
    category_id: Optional[int] = None
    transaction_kind: Optional[str] = None


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    parent: Optional[str] = None


class RuleCreate(BaseModel):
    pattern: str
    category_id: int
    priority: int = 0


class RuleRead(RuleCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)


class RuleUpdate(BaseModel):
    pattern: Optional[str] = None
    category_id: Optional[int] = None
    priority: Optional[int] = None


class BatchRead(BaseModel):
    id: int
    profile: str
    filename: str
    account_id: Optional[int] = None
    created_at: dt.datetime
    staged: int
    skipped: int
    committed: int = 0
    file_kind: str = "mixed"
    status: str = "active"
    rolled_back_at: Optional[dt.datetime] = None
    model_config = ConfigDict(from_attributes=True)


class BatchDetailRead(BatchRead):
    by_status: dict[str, int]
    by_kind: dict[str, int] = {}
    mapping: dict = {}

    @field_validator("mapping", mode="before")
    @classmethod
    def _parse_mapping(cls, v):
        import json
        return json.loads(v) if isinstance(v, str) else v


class StagingRowRead(BaseModel):
    id: int
    batch_id: int
    account_id: Optional[int] = None
    date: dt.date
    merchant: str
    amount_cents: int
    category_id: Optional[int] = None
    category_source: Optional[str] = None
    note: Optional[str] = None
    status: str
    row_kind: str = "spend"
    transaction_kind: str = "expense"
    row_detail: str = ""

    model_config = ConfigDict(from_attributes=True)


class HoldingCreate(BaseModel):
    symbol: str
    name: Optional[str] = None
    account_id: Optional[int] = None
    quantity_milli: int = 0
    price_cents: int = 0


class HoldingRead(HoldingCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)
