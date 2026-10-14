"""Central logging: `PERFI_LOG_LEVEL` (default INFO), one stderr stream."""
import logging
import os

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def _perfi_handler():
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATEFMT))
    handler._perfi_owned = True
    return handler


def setup():
    # Own root output: import side effects and Alembic's fileConfig
    # (lifespan) install their own root handlers with their own formats
    # (Alembic's has no timestamp at all). Evict everything except our
    # handler and pytest's capture handler, so perfi lines always carry a
    # human-readable timestamp. Safe to call repeatedly (lifespan
    # re-asserts after Alembic) and under pytest (caplog keeps working).
    level = getattr(logging, os.environ.get("PERFI_LOG_LEVEL", "INFO").upper(),
                    logging.INFO)
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_perfi_owned", False):
            continue
        if type(handler).__module__.partition(".")[0] in ("_pytest", "pytest"):
            continue
        root.removeHandler(handler)
    if not any(getattr(handler, "_perfi_owned", False) for handler in root.handlers):
        root.addHandler(_perfi_handler())
    root.setLevel(level)


def get(name):
    setup()
    return logging.getLogger(f"perfi.{name}")
