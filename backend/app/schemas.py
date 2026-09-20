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
    account_id: int
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
    account_id: int
    created_at: dt.datetime
    staged: int
    skipped: int
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
    trade_json: dict = {}

    @field_validator("trade_json", mode="before")
    @classmethod
    def _parse_trade_json(cls, v):
        import json
        if isinstance(v, str):
            try:
                return json.loads(v) if v else {}
            except ValueError:
                return {}
        return v or {}

    model_config = ConfigDict(from_attributes=True)


class BudgetCreate(BaseModel):
    category_id: int
    month: str
    limit_cents: int
    rollover: bool = False


class BudgetRead(BudgetCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)


class BudgetUpdate(BaseModel):
    limit_cents: Optional[int] = None
    rollover: Optional[bool] = None


class RecurringCreate(BaseModel):
    name: str
    amount_cents: int
    cadence: str = "monthly"
    next_due: dt.date


class RecurringRead(RecurringCreate):
    id: int
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


class OrderCreate(BaseModel):
    account_id: int
    symbol: str
    side: str
    quantity_milli: int
    price_cents: int
    fees_cents: int = 0
    executed_at: dt.date
    linked_transaction_id: Optional[int] = None


class OrderRead(OrderCreate):
    id: int
    proceeds_cents: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)


class SavedReportCreate(BaseModel):
    name: str
    type: str
    params: dict = {}


class SavedReportRead(SavedReportCreate):
    id: int
    created_at: dt.datetime
    model_config = ConfigDict(from_attributes=True)

    @field_validator("params", mode="before")
    @classmethod
    def _parse_params(cls, v):
        import json
        return json.loads(v) if isinstance(v, str) else v


class AISettingsRead(BaseModel):
    provider: str
    model: str
    base_url: str
    has_key: bool


class AISettingsUpdate(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
