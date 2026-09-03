"""Fernet encryption for stored secrets (AI API key).

Key resolution: PERFI_ENCRYPTION_KEY env wins; otherwise data/.ai_key next to
the database (created on first use, mode 0600). Losing the key orphans
whatever it encrypted — back up data/ with the database.
"""
import os

from cryptography.fernet import Fernet

from ..database import REPO_ROOT

_KEY = None


def _valid_key(raw):
    try:
        Fernet(raw)
        return True
    except Exception:
        return False


def _load_or_create_key():
    env = os.environ.get("PERFI_ENCRYPTION_KEY")
    if env:
        raw = env.encode() if isinstance(env, str) else env
        if not _valid_key(raw):
            raise RuntimeError("PERFI_ENCRYPTION_KEY is not a valid Fernet key. "
                               "Generate one with: python -c "
                               "'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'")
        return raw
    path = os.path.join(REPO_ROOT, "data", ".ai_key")
    if os.path.exists(path):
        with open(path, "rb") as f:
            raw = f.read().strip()
        if raw and not _valid_key(raw):
            raise RuntimeError(
                f"{path} is not a valid Fernet key. Restore it from backup "
                f"(losing it orphans encrypted secrets) or delete it to start fresh.")
        if raw:
            return raw
        # empty file encrypts nothing: fall through and regenerate
    os.makedirs(os.path.dirname(path), exist_ok=True)
    key = Fernet.generate_key()
    with open(path, "wb") as f:
        f.write(key)
    os.chmod(path, 0o600)
    return key


def _fernet():
    global _KEY
    if _KEY is None:
        _KEY = _load_or_create_key()
    return Fernet(_KEY)


def encrypt(plaintext):
    return _fernet().encrypt((plaintext or "").encode()).decode()


def decrypt(token):
    return _fernet().decrypt(token.encode()).decode()
