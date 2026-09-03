import json

import pytest
from cryptography.fernet import Fernet

from app.services import ai_provider, encryption
from conftest import make_txn


@pytest.fixture
def isolated_key(monkeypatch):
    monkeypatch.setenv("PERFI_ENCRYPTION_KEY", Fernet.generate_key().decode())
    encryption._KEY = None
    yield
    encryption._KEY = None


def test_encryption_roundtrip(isolated_key):
    token = encryption.encrypt("sk-secret")
    assert token != "sk-secret"
    assert encryption.decrypt(token) == "sk-secret"


def test_ai_settings_key_never_exposed(store, client):
    body = client.get("/api/settings/ai").json()
    assert body == {"provider": "openai", "model": "", "base_url": "", "has_key": False}

    assert client.put("/api/settings/ai", json={"provider": "nope"}).status_code == 422
    body = client.put("/api/settings/ai", json={
        "provider": "anthropic", "model": "m", "api_key": "sk-x"}).json()
    assert body == {"provider": "anthropic", "model": "m", "base_url": "", "has_key": True}
    assert "sk-x" not in json.dumps(client.get("/api/settings/ai").json())


def test_categorize_needs_key(store, client):
    assert client.post("/api/ai/categorize").status_code == 409


FAKE_REPLY = {
    "Mystery Grocer": {"category": "Groceries", "confidence": 0.9},
    "Shady Diner": {"category": "Dining", "confidence": 0.2},
    "Bogus Place": {"category": "Nonexistent", "confidence": 0.99},
}


def test_categorize_gated_and_manual_safe(store, client, monkeypatch, isolated_key):
    acct = store["acct"]
    unc = store["cats"]["Uncategorized"]
    g = store["cats"]["Groceries"]
    t_unc = make_txn(client, acct, unc, -1000, "Mystery Grocer", "2026-01-05")
    t_low = make_txn(client, acct, unc, -2000, "Shady Diner", "2026-01-06")
    t_bad = make_txn(client, acct, unc, -3000, "Bogus Place", "2026-01-07")
    t_manual = make_txn(client, acct, unc, -4000, "Mystery Grocer", "2026-01-08")
    client.patch(f"/api/transactions/{t_manual['id']}", json={"category_id": g})

    client.put("/api/settings/ai", json={"provider": "custom", "model": "m",
                                          "base_url": "http://x", "api_key": "k"})
    monkeypatch.setattr(ai_provider, "complete",
                        lambda *a, **k: "```json\n" + json.dumps(FAKE_REPLY) + "\n```")

    out = client.post("/api/ai/categorize?limit=10&min_confidence=0.7").json()
    assert [a["id"] for a in out["applied"]] == [t_unc["id"]]
    assert out["applied"][0]["category"] == "Groceries"
    skipped = {s["id"]: s["reason"] for s in out["skipped"]}
    assert "confidence" in skipped[t_low["id"]]
    assert "unknown category" in skipped[t_bad["id"]]

    got = client.get(f"/api/transactions/{t_unc['id']}").json()
    assert got["category_id"] == g and got["category_source"] == "ai"
    kept = client.get(f"/api/transactions/{t_manual['id']}").json()
    assert kept["category_id"] == g and kept["category_source"] == "manual"


def test_suggest_rejects_non_json():
    import pytest as pt
    with pt.raises(RuntimeError):
        ai_provider.suggest_categories(["A"], ["Groceries"], lambda p: "not json")
