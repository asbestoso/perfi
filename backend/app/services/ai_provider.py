"""BYOK chat completions for categorization. urllib only, no vendor SDKs.

Supported providers: openai, anthropic, google, custom (OpenAI-compatible
base URL). The model name is user configuration, not code — defaults below
are starting points that will go stale.
"""
import json
import urllib.request

from ..logging_setup import get as get_log
from . import settings_store

log = get_log("ai")

PROVIDERS = ("openai", "anthropic", "google", "custom")

DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5",
    "google": "gemini-2.0-flash",
    "custom": "",
}

DEFAULT_BASES = {
    "openai": "https://api.openai.com/v1",
    "custom": "",
}


def _post(url, headers, body, timeout=90):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"provider error {e.code}: {e.read().decode()[:300]}")


def complete(provider, api_key, model, messages, base_url="", system="", timeout=90):
    if provider in ("openai", "custom"):
        base = (base_url or DEFAULT_BASES.get(provider, "")).rstrip("/")
        if not base:
            raise RuntimeError("custom provider needs base_url")
        body = {"model": model, "messages": messages, "temperature": 0}
        if system:
            body["messages"] = [{"role": "system", "content": system}] + messages
        data = _post(base + "/chat/completions", {"Authorization": f"Bearer {api_key}"}, body, timeout)
        return data["choices"][0]["message"]["content"]
    if provider == "anthropic":
        body = {"model": model, "max_tokens": 2000, "messages": messages}
        if system:
            body["system"] = system
        data = _post("https://api.anthropic.com/v1/messages",
                     {"x-api-key": api_key, "anthropic-version": "2023-06-01"}, body, timeout)
        return "".join(b.get("text", "") for b in data.get("content", []))
    if provider == "google":
        body = {"contents": [{"role": "user", "parts": [{"text": m["content"]}]}
                             for m in messages if m["role"] == "user"]}
        if system:
            body["system_instruction"] = {"parts": [{"text": system}]}
        data = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
                     f":generateContent?key={api_key}", {}, body, timeout)
        cands = data.get("candidates", [])
        parts = (cands[0].get("content", {}).get("parts", []) if cands else [])
        return "".join(p.get("text", "") for p in parts)
    raise RuntimeError(f"unknown provider: {provider}")


PROMPT = ("You categorize bank transactions. Reply with ONLY a JSON object mapping "
          "each merchant to {{\"category\": <one of: {cats}>, \"confidence\": 0.0-1.0}}. "
          "Use \"Uncategorized\" with low confidence when unsure. Merchants: {merchants}")


def suggest_categories(merchants, categories, complete_fn):
    cats = ", ".join(sorted(set(categories)))
    text = complete_fn(PROMPT.format(
        cats=cats, merchants=json.dumps(sorted(set(merchants)))))
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    try:
        data = json.loads(text)
    except ValueError:
        raise RuntimeError("provider did not return JSON")
    out = {}
    for m, v in (data if isinstance(data, dict) else {}).items():
        if isinstance(v, dict) and "category" in v:
            try:
                out[m] = (v["category"], float(v.get("confidence", 0)))
            except (TypeError, ValueError):
                continue
    return out


def categorize_uncategorized(db, limit=20, min_confidence=0.7, complete_fn=None):
    from fastapi import HTTPException
    from ..models import Category, Transaction
    cfg = settings_store.get_ai_config(db)
    api_key = settings_store.get_api_key(db)
    if not api_key:
        raise HTTPException(status_code=409, detail="no AI API key configured (PUT /api/settings/ai)")
    model = cfg["model"] or DEFAULT_MODELS[cfg["provider"]]
    if not model:
        raise HTTPException(status_code=409, detail="no AI model configured (PUT /api/settings/ai)")
    complete_fn = complete_fn or (lambda prompt: complete(
        cfg["provider"], api_key, model,
        [{"role": "user", "content": prompt}], cfg["base_url"]))
    # Only never-categorized rows: manual/rule/import/merchant work is never touched.
    rows = db.query(Transaction).filter(Transaction.category_source.is_(None)).limit(max(1, limit)).all()
    if not rows:
        return {"applied": [], "skipped": []}
    cats = {c.name: c.id for c in db.query(Category).all()}
    by_lower = {n.lower(): n for n in cats}
    suggestions = suggest_categories([t.merchant for t in rows], list(cats), complete_fn)
    applied, skipped = [], []
    for t in rows:
        hit = suggestions.get(t.merchant)
        if hit is None:
            skipped.append({"id": t.id, "reason": "no suggestion"})
            continue
        name, conf = hit
        canonical = by_lower.get((name or "").strip().lower())
        if canonical is None:
            skipped.append({"id": t.id, "reason": f"unknown category: {name}"})
            continue
        if conf < min_confidence:
            skipped.append({"id": t.id, "reason": f"confidence {conf} < {min_confidence}"})
            continue
        t.category_id, t.category_source = cats[canonical], "ai"
        applied.append({"id": t.id, "category": canonical, "confidence": conf})
    db.commit()
    log.info(f"ai categorize ({cfg['provider']}): applied={len(applied)} skipped={len(skipped)}")
    return {"applied": applied, "skipped": skipped}
