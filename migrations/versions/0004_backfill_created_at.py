"""Backfill missing timestamp columns.

Revision ID: 0004_backfill_created_at
Revises: 0003_vault_otp_attempts
Create Date: 2026-11-10

The initial migration created several tables without the timestamp columns
their ORM models declare, which made every INSERT into them fail with
"no such column: created_at".

Affected tables:
  - ``quotas``             had updated_at, missing created_at
  - ``vault_sessions``     missing both
  - ``scenario_instances`` missing both
  - ``vip_subscriptions``  had created_at, missing updated_at
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_backfill_created_at"
down_revision: Union[str, None] = "0003_vault_otp_attempts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tables that need created_at, and whether they still need updated_at.
# (table, needs_created_at, needs_updated_at)
TARGETS = [
    ("quotas", True, False),
    ("vault_sessions", True, True),
    ("scenario_instances", True, True),
    ("vip_subscriptions", False, True),
]


def _has_column(conn, table: str, column: str) -> bool:
    """Check whether a column exists, in a dialect-agnostic way."""
    inspector = sa.inspect(conn)
    if table not in inspector.get_table_names():
        return False
    return any(c["name"] == column for c in inspector.get_columns(table))


def upgrade() -> None:
    """Add the missing created_at (and updated_at) columns."""
    conn = op.get_bind()

    for table, need_created, need_updated in TARGETS:
        if need_created and not _has_column(conn, table, "created_at"):
            op.add_column(
                table,
                sa.Column(
                    "created_at",
                    sa.DateTime(timezone=True),
                    nullable=False,
                    server_default=sa.func.now(),
                ),
            )
        if need_updated and not _has_column(conn, table, "updated_at"):
            op.add_column(
                table,
                sa.Column(
                    "updated_at",
                    sa.DateTime(timezone=True),
                    nullable=False,
                    server_default=sa.func.now(),
                ),
            )


def downgrade() -> None:
    """Drop the backfilled columns."""
    conn = op.get_bind()

    for table, need_created, need_updated in reversed(TARGETS):
        if need_updated and _has_column(conn, table, "updated_at"):
            op.drop_column(table, "updated_at")
        if need_created and _has_column(conn, table, "created_at"):
            op.drop_column(table, "created_at")
