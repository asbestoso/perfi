"""SQLite engine (WAL) + session factory + init."""
import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from alembic.config import Config
from alembic import command

from .logging_setup import get as get_log

log = get_log("db")


class Base(DeclarativeBase):
    pass


# Absolute path so the app, Alembic, and tests always use the same file
# no matter which directory the process starts from.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(REPO_ROOT, "data", "perfi.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})

@event.listens_for(engine, "connect")
def _set_wal(dbapi_conn, _rec):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL;")
    cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _alembic_ini():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(here), "alembic.ini")


def init_db():
    from sqlalchemy import inspect, text
    from .seed import seed_categories
    ini = _alembic_ini()
    cfg = Config(ini)
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(ini), "alembic"))
    with engine.connect() as conn:
        tables = set(inspect(conn).get_table_names())
        versioned = (
            "alembic_version" in tables
            and conn.execute(text("select version_num from alembic_version")).first() is not None
        )
    if "accounts" in tables and not versioned:
        # Pre-Alembic DB built by create_all: schema matches the initial
        # revision, so stamp instead of migrating.
        command.stamp(cfg, "head")
        log.info("stamped pre-Alembic database to head")
    else:
        command.upgrade(cfg, "head")
        log.info("database migrated to head")
    db = SessionLocal()
    try:
        seed_categories(db)
    finally:
        db.close()
