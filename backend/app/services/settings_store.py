"""User settings store. ai.api_key is kept Fernet-encrypted at rest."""
from . import encryption
from ..models import UserSetting

PROVIDERS = ("openai", "anthropic", "google", "custom")


def get_setting(db, key, default=""):
    row = db.get(UserSetting, key)
    return row.value if row is not None else default


def set_setting(db, key, value):
    row = db.get(UserSetting, key)
    if row is None:
        row = UserSetting(key=key, value=value or "")
        db.add(row)
    else:
        row.value = value or ""
    db.commit()


def get_ai_config(db):
    from fastapi import HTTPException
    provider = get_setting(db, "ai.provider") or "openai"
    if provider not in PROVIDERS:
        raise HTTPException(status_code=422, detail=f"unknown provider: {provider}")
    return {"provider": provider,
            "model": get_setting(db, "ai.model"),
            "base_url": get_setting(db, "ai.base_url"),
            "has_key": bool(get_setting(db, "ai.api_key"))}


def set_ai_config(db, provider=None, model=None, base_url=None, api_key=None):
    from fastapi import HTTPException
    if provider is not None:
        if provider not in PROVIDERS:
            raise HTTPException(status_code=422, detail=f"unknown provider: {provider}")
        set_setting(db, "ai.provider", provider)
    if model is not None:
        set_setting(db, "ai.model", model)
    if base_url is not None:
        set_setting(db, "ai.base_url", base_url)
    if api_key is not None:
        set_setting(db, "ai.api_key", encryption.encrypt(api_key))
    return get_ai_config(db)


def get_api_key(db):
    token = get_setting(db, "ai.api_key")
    return encryption.decrypt(token) if token else ""
