import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.database import Base
from app.main import app


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)

    def override():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def store(client):
    cats = {}
    for name in ("Groceries", "Dining", "Income", "Uncategorized"):
        r = client.post("/api/categories", json={"name": name})
        assert r.status_code == 200
        cats[name] = r.json()["id"]
    accts = []
    for name in ("Checking", "Card"):
        r = client.post("/api/accounts", json={"name": name, "balance_cents": 0})
        assert r.status_code == 200
        accts.append(r.json()["id"])
    return {"cats": cats, "acct": accts[0], "accts": accts}


def make_txn(client, aid, cid, cents, merchant, date):
    r = client.post("/api/transactions", json={
        "account_id": aid, "category_id": cid, "amount_cents": cents,
        "merchant": merchant, "date": date})
    assert r.status_code == 200
    return r.json()


#: Verbatim Robinhood activity sample (redacted user paste) for the
#: brokerage-activity scan/import tests.
ROBINHOOD_ACTIVITY_CSV = (
    '"Activity Date","Process Date","Settle Date","Instrument","Description",'
    '"Trans Code","Quantity","Price","Amount"\n'
    '"12/29/2023","12/29/2023","12/29/2023","VNM",'
    '"Cash Div: R/D 2023-12-28 P/D 2023-12-29 - 45 shares at 0.0185",'
    '"CDIV","","","$0.83"\n'
    '"12/29/2023","12/29/2023","12/29/2023","","Interest Payment",'
    '"INT","","","$13.50"\n'
    '"12/27/2023","12/27/2023","12/27/2023","VTI",'
    '"Cash Div: R/D 2023-12-22 P/D 2023-12-27 - 47 shares at 1.0017",'
    '"CDIV","","","$47.08"\n'
)
