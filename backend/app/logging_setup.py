"""Central logging: `PERFI_LOG_LEVEL` (default INFO), one stderr stream."""
import logging
import os

_configured = False


def setup():
    global _configured
    # basicConfig() is a no-op when root already has handlers (import side
    # effects, test runners), which silently leaves the level at WARNING.
    # Configure explicitly instead. The level is re-asserted on every call
    # because lifespan runs Alembic in-process and its fileConfig resets root.
    level = getattr(logging, os.environ.get("PERFI_LOG_LEVEL", "INFO").upper(),
                    logging.INFO)
    root = logging.getLogger()
    if not _configured:
        if not root.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"))
            root.addHandler(handler)
        _configured = True
    root.setLevel(level)


def get(name):
    setup()
    return logging.getLogger(f"perfi.{name}")
