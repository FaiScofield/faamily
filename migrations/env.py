"""Alembic environment configuration.

Resolves the target database from (in order of precedence):
  1. an explicit ``sqlalchemy.url`` passed in the Alembic Config (used by
     tests and by tooling that needs to target a specific database)
  2. the ``DATABASE_URL`` environment variable / application settings

Applies migrations against the target database.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings

# Alembic Config object
config = context.config

# Resolve the URL: an explicitly supplied one wins over the app settings.
# This keeps `alembic upgrade head` working with just DATABASE_URL set,
# while letting tests point the migration chain at a throwaway database.
# The placeholder in alembic.ini counts as "not supplied" — it is detected by
# its scheme rather than matched literally, so editing alembic.ini later
# cannot silently break this.
_configured_url = config.get_main_option("sqlalchemy.url") or ""
_is_placeholder = not _configured_url or "driver://" in _configured_url
if _is_placeholder:
    config.set_main_option("sqlalchemy.url", settings.database_url)

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# MetaData target for 'autogenerate' support
# Import all ORM models here so that their metadata is registered
from sqlalchemy.dialects.postgresql import JSONB as _PG_JSONB

# Register SQLite-compatible type compilations for local dev
from sqlalchemy.dialects.postgresql import UUID as _PG_UUID
from sqlalchemy.ext.compiler import compiles

from app.models import Base  # noqa: E402

if settings.database_url.startswith("sqlite"):
    @compiles(_PG_UUID, "sqlite")
    def _compile_uuid_sqlite(type_, compiler, **kw):
        return "VARCHAR(36)"

    @compiles(_PG_JSONB, "sqlite")
    def _compile_jsonb_sqlite(type_, compiler, **kw):
        return "JSON"


target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures the context with just a URL and not an Engine.
    Calls to context.execute() emit the given string to the script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Creates an Engine and associates a connection with the context.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
