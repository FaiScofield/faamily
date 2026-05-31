"""Add account email OTP table and align schema drift.

Revision ID: 0002_email_otp_schema_fix
Revises: 0001_init
Create Date: 2026-05-31
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "0002_email_otp_schema_fix"
down_revision: Union[str, None] = "0001_init"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply account email OTP storage and targeted schema corrections."""
    op.create_table(
        "email_verification_otps",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "idx_email_verification_otps_email_expires",
        "email_verification_otps",
        ["email", "expires_at"],
    )

    op.execute(
        """
        update memberships
        set role = 'member',
            permissions = coalesce(permissions, '{}'::jsonb) || '{"restricted": true}'::jsonb
        where role = 'child'
        """
    )
    op.drop_constraint("chk_memberships_role", "memberships", type_="check")
    op.create_check_constraint(
        "chk_memberships_role",
        "memberships",
        "role IN ('owner', 'admin', 'member')",
    )

    op.drop_constraint("uq_folders_family_zone_parent_name", "folders", type_="unique")
    op.create_index(
        "uq_folders_family_zone_parent_name",
        "folders",
        ["family_id", "zone", "parent_id", "name"],
        unique=True,
    )

    op.alter_column("files", "size_bytes", existing_type=sa.Integer(), type_=sa.BigInteger())
    op.alter_column("quotas", "total_bytes", existing_type=sa.Integer(), type_=sa.BigInteger())
    op.alter_column("quotas", "used_bytes", existing_type=sa.Integer(), type_=sa.BigInteger())


def downgrade() -> None:
    """Remove account email OTP storage and revert compatible schema changes."""
    op.alter_column("quotas", "used_bytes", existing_type=sa.BigInteger(), type_=sa.Integer())
    op.alter_column("quotas", "total_bytes", existing_type=sa.BigInteger(), type_=sa.Integer())
    op.alter_column("files", "size_bytes", existing_type=sa.BigInteger(), type_=sa.Integer())

    op.drop_index("uq_folders_family_zone_parent_name", table_name="folders")
    op.create_unique_constraint(
        "uq_folders_family_zone_parent_name",
        "folders",
        ["family_id", "zone", "name"],
    )

    op.drop_constraint("chk_memberships_role", "memberships", type_="check")
    op.create_check_constraint(
        "chk_memberships_role",
        "memberships",
        "role IN ('owner', 'admin', 'member', 'child')",
    )

    op.drop_index("idx_email_verification_otps_email_expires", table_name="email_verification_otps")
    op.drop_table("email_verification_otps")
