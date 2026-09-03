import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, event, pool

from alembic import context

# backend/ on sys.path so `app.*` imports work wherever alembic runs from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

config = context.config

if config.config_file_name is not None:
    # Never disable the app's loggers: lifespan runs migrations in-process.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

from app import models  # noqa: F401  (register tables)
from app.database import Base

target_metadata = Base.metadata

# Absolute DB path: <repo>/data/perfi.db, so migrate works from any CWD.
# PERFI_ALEMBIC_URL overrides it (used to autogenerate against an empty DB).
_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_db_path = os.path.join(_repo_root, "data", "perfi.db")
config.set_main_option("sqlalchemy.url", os.environ.get("PERFI_ALEMBIC_URL", "sqlite:///" + _db_path))


def _set_wal(dbapi_conn, _rec):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL;")
    cur.close()


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    event.listen(connectable, "connect", _set_wal)

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
