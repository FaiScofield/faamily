"""Add vault OTP attempt counter for brute-force protection.

Revision ID: 0003_vault_otp_attempts
Revises: 0002_email_otp_schema_fix
Create Date: 2026-11-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_vault_otp_attempts"
down_revision: Union[str, None] = "0002_email_otp_schema_fix"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Track failed verification attempts per vault OTP.

    Also backfills the `updated_at` columns that the initial migration
    omitted but the ORM models declare (via TimestampMixin).
    """
    conn = op.get_bind()
    is_sqlite = conn.dialect.name == "sqlite"

    op.add_column(
        "vault_email_otps",
        sa.Column(
            "attempts",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    if not is_sqlite:
        op.create_check_constraint(
            "chk_vault_email_otps_attempts",
            "vault_email_otps",
            "attempts >= 0",
        )

    # Backfill updated_at on tables whose ORM model uses TimestampMixin
    for table in ("task_submissions", "vault_email_otps", "vault_sessions", "scenario_instances"):
        _add_updated_at(table, is_sqlite)


def _add_updated_at(table: str, is_sqlite: bool) -> None:
    """Add an `updated_at` column mirroring `created_at` semantics."""
    if is_sqlite:
        op.add_column(
            table,
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        return

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
    """Drop the attempt counter and the backfilled updated_at columns."""
    conn = op.get_bind()
    is_sqlite = conn.dialect.name == "sqlite"

    if not is_sqlite:
        op.drop_constraint(
            "chk_vault_email_otps_attempts",
            "vault_email_otps",
            type_="check",
        )

    op.drop_column("vault_email_otps", "attempts")

    for table in ("task_submissions", "vault_email_otps", "vault_sessions", "scenario_instances"):
        op.drop_column(table, "updated_at")
