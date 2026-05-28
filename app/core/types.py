"""
Cross-database type compatibility layer.

Provides a GUID type that works with both PostgreSQL (native UUID)
and SQLite (CHAR(36) fallback), so developers can run the app
locally without Docker or PostgreSQL.
"""

import uuid

from sqlalchemy import event
from sqlalchemy import types as sa_types
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.engine import Engine


class GUID(sa_types.TypeDecorator):
    """
    Platform-independent GUID/UUID type.

    Uses PostgreSQL's native UUID type when connected to PostgreSQL,
    and falls back to CHAR(36) for SQLite and other databases.
    """

    impl = sa_types.CHAR(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(sa_types.CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value  # PG driver handles UUID natively
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value  # PG driver returns uuid.UUID
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(value)


# ---------------------------------------------------------------------------
# SQLite compatibility events
# ---------------------------------------------------------------------------


def _enable_sqlite_compat(engine: Engine) -> None:
    """Register event listeners for SQLite compatibility."""

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        """Enable foreign keys and WAL mode for SQLite."""
        import sqlite3

        if isinstance(dbapi_connection, sqlite3.Connection):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()


def configure_engine(engine: Engine) -> None:
    """Apply database-specific configuration to an engine.

    Call this after creating the engine for compatibility setup.
    """
    if engine.dialect.name == "sqlite":
        _enable_sqlite_compat(engine)
        _register_sqlite_compiles()


def _register_sqlite_compiles():
    """Register SQLAlchemy type compilation rules for SQLite."""
    from sqlalchemy.ext.compiler import compiles
    from sqlalchemy.dialects.postgresql import JSONB

    @compiles(PG_JSONB, "sqlite")
    def _compile_jsonb_sqlite(type_, compiler, **kw):
        """Map PostgreSQL JSONB to SQLite JSON."""
        return compiler.visit_JSON(type_, **kw)

    # UUID is handled by the GUID type class, but ensure
    # raw PG_UUID references also compile for SQLite
    @compiles(PG_UUID, "sqlite")
    def _compile_uuid_sqlite(type_, compiler, **kw):
        return "VARCHAR(36)"
