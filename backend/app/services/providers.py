"""Phase-2 provider adapters (Plaid / SimpleFIN). Env-gated stubs.

Set PERFI_PLAID_ENABLED=1 / PERFI_SIMPLEFIN_ENABLED=1 in phase 2 with real
credentials; phase 1 raises ProviderDisabledError so no bank sync can run.
Phase 2: install plaid-python / requests, implement sync + webhooks here.
"""
from ..config import settings


class ProviderDisabledError(RuntimeError):
    pass


def plaid_sync():
    if not settings.plaid_enabled:
        raise ProviderDisabledError("Plaid disabled (phase 2). Set PERFI_PLAID_ENABLED=1.")
    raise NotImplementedError("phase 2")


def simplefin_sync():
    if not settings.simplefin_enabled:
        raise ProviderDisabledError("SimpleFIN disabled (phase 2). Set PERFI_SIMPLEFIN_ENABLED=1.")
    raise NotImplementedError("phase 2")
