"""Schema consistency tests.

The initial migration created three tables without a ``created_at`` column
even though their ORM models use ``TimestampMixin``. Any INSERT into those
tables failed with "no such column: created_at" — a 500 that only surfaced
once the app was exercised against a migrated database.

These tests build the schema from the migration chain and assert that every
model table has exactly the columns the ORM expects.
"""

import pytest
import sqlalchemy as sa

from app.models import Base


@pytest.fixture(scope="module")
def migrated_engine(tmp_path_factory):
    """A SQLite engine whose schema comes from the migration chain.

    A file-backed database is required: Alembic opens its own connection, and
    an in-memory SQLite database is private to each connection, so the tables
    would not be visible afterwards.
    """
    from alembic import command
    from alembic.config import Config

    db_path = tmp_path_factory.mktemp("migrated") / "schema_check.db"
    url = f"sqlite:///{db_path.as_posix()}"

    engine = sa.create_engine(url)
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

    yield engine

    engine.dispose()


def test_migration_chain_produces_every_model_table(migrated_engine):
    """Every table declared in the ORM exists after migrating to head."""
    inspector = sa.inspect(migrated_engine)
    db_tables = set(inspector.get_table_names())
    model_tables = set(Base.metadata.tables.keys())

    missing = model_tables - db_tables
    assert not missing, f"迁移后缺少表: {sorted(missing)}"


@pytest.mark.parametrize("table", sorted(Base.metadata.tables.keys()))
def test_orm_columns_exist_in_migrated_schema(migrated_engine, table):
    """Every column the ORM declares exists in the migrated database.

    Regression test for the "no such column: created_at" 500 that hit
    quotas, vault_sessions and scenario_instances.
    """
    inspector = sa.inspect(migrated_engine)
    assert table in inspector.get_table_names(), f"表 {table} 不存在"

    db_columns = {c["name"] for c in inspector.get_columns(table)}
    model_columns = {c.name for c in Base.metadata.tables[table].columns}

    missing = model_columns - db_columns
    assert not missing, f"{table} 缺少 ORM 声明的列: {sorted(missing)}"


@pytest.mark.parametrize(
    "table",
    [
        "users",
        "user_identities",
        "families",
        "memberships",
        "invites",
        "announcements",
        "tasks",
        "task_submissions",
        "folders",
        "files",
        "quotas",
        "vault_email_otps",
        "vault_sessions",
        "scenario_templates",
        "scenario_instances",
    ],
)
def test_timestamp_mixin_tables_have_both_columns(migrated_engine, table):
    """Tables using TimestampMixin must have created_at and updated_at.

    These are exactly the models that declare TimestampMixin, so both
    columns are mandatory — a missing one breaks every INSERT.
    """
    inspector = sa.inspect(migrated_engine)
    columns = {c["name"] for c in inspector.get_columns(table)}

    for expected in ("created_at", "updated_at"):
        assert expected in columns, f"{table} 缺少 {expected} 列"


def test_migrated_schema_has_no_extra_tables(migrated_engine):
    """The migration chain does not leave orphan tables behind."""
    inspector = sa.inspect(migrated_engine)
    db_tables = set(inspector.get_table_names())
    # alembic's own bookkeeping table is expected
    db_tables.discard("alembic_version")
    db_tables.discard("sqlite_sequence")

    model_tables = set(Base.metadata.tables.keys())
    extra = db_tables - model_tables
    assert not extra, f"迁移后多出表: {sorted(extra)}"
