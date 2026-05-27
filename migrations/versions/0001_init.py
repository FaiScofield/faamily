"""Initial schema: all MVP tables from the original schema.sql.

Revision ID: 0001_init
Revises: None
Create Date: 2026-05-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "0001_init"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgcrypto extension for gen_random_uuid()
    op.execute("create extension if not exists pgcrypto")

    # -----------------------------------------------------------------------
    # users
    # -----------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("status", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_users_status", "users", ["status"])

    # -----------------------------------------------------------------------
    # user_identities
    # -----------------------------------------------------------------------
    op.create_table(
        "user_identities",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("identifier", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extra", JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_check_constraint("chk_user_identities_type", "user_identities", "type IN ('wechat', 'phone', 'email')")
    op.create_unique_constraint("uq_user_identities_type_identifier", "user_identities", ["type", "identifier"])
    op.create_index("idx_user_identities_user_id", "user_identities", ["user_id"])
    op.create_index("idx_user_identities_type", "user_identities", ["type"])

    # -----------------------------------------------------------------------
    # families
    # -----------------------------------------------------------------------
    op.create_table(
        "families",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("owner_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_families_owner_user_id", "families", ["owner_user_id"])

    # -----------------------------------------------------------------------
    # memberships
    # -----------------------------------------------------------------------
    op.create_table(
        "memberships",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("family_id", UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_check_constraint("chk_memberships_role", "memberships", "role IN ('owner', 'admin', 'member', 'child')")
    op.create_check_constraint("chk_memberships_status", "memberships", "status IN ('active', 'pending', 'removed')")
    op.create_unique_constraint("uq_memberships_family_user", "memberships", ["family_id", "user_id"])
    op.create_index("idx_memberships_family_role", "memberships", ["family_id", "role"])
    op.create_index("idx_memberships_user_id", "memberships", ["user_id"])

    # -----------------------------------------------------------------------
    # invites
    # -----------------------------------------------------------------------
    op.create_table(
        "invites",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("family_id", UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.Text(), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("need_approval", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_check_constraint("chk_invites_max_uses", "invites", "max_uses >= 1")
    op.create_check_constraint("chk_invites_used_count", "invites", "used_count >= 0")
    op.create_index("idx_invites_family_expires", "invites", ["family_id", "expires_at"])

    # -----------------------------------------------------------------------
    # announcements
    # -----------------------------------------------------------------------
    op.create_table(
        "announcements",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("family_id", UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_announcements_family_created", "announcements", ["family_id", sa.text("created_at DESC")])
    op.create_index("idx_announcements_family_pinned", "announcements", ["family_id", "pinned"])

    # -----------------------------------------------------------------------
    # tasks
    # -----------------------------------------------------------------------
    op.create_table(
        "tasks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("family_id", UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("assignee_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewer_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("priority", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("repeat_rule", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "chk_tasks_status", "tasks",
        "status IN ('pending', 'in_progress', 'submitted', 'done', 'rejected')",
    )
    op.create_index("idx_tasks_family_status_due", "tasks", ["family_id", "status", "due_at"])
    op.create_index("idx_tasks_family_assignee_status", "tasks", ["family_id", "assignee_user_id", "status"])
    op.create_index("idx_tasks_family_created", "tasks", ["family_id", sa.text("created_at DESC")])

    # -----------------------------------------------------------------------
    # task_submissions
    # -----------------------------------------------------------------------
    op.create_table(
        "task_submissions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("family_id", UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", UUID(as_uuid=True), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("submitted_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="submitted"),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_check_constraint(
        "chk_task_submissions_status", "task_submissions",
        "status IN ('submitted', 'approved', 'rejected')",
    )
    op.create_index("idx_task_submissions_task_created", "task_submissions", ["task_id", sa.text("created_at DESC")])

    # -----------------------------------------------------------------------
    # folders
    # -----------------------------------------------------------------------
    op.create_table(
        "folders",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("family_id", UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), nullable=False),
        sa.Column("zone", sa.String(20), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("parent_id", UUID(as_uuid=True), sa.ForeignKey("folders.id", ondelete="CASCADE"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_check_constraint("chk_folders_zone", "folders", "zone IN ('shared', 'vault')")
    op.create_unique_constraint("uq_folders_family_zone_parent_name", "folders", ["family_id", "zone", "name"])
    op.create_index("idx_folders_family_zone", "folders", ["family_id", "zone"])

    # -----------------------------------------------------------------------
    # files
    # -----------------------------------------------------------------------
    op.create_table(
        "files",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("family_id", UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), nullable=False),
        sa.Column("zone", sa.String(20), nullable=False),
        sa.Column("folder_id", UUID(as_uuid=True), sa.ForeignKey("folders.id", ondelete="SET NULL"), nullable=True),
        sa.Column("owner_type", sa.String(30), nullable=False),
        sa.Column("owner_id", UUID(as_uuid=True), nullable=True),
        sa.Column("uploader_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("storage_key", sa.Text(), nullable=False, unique=True),
        sa.Column("checksum", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint("chk_files_zone", "files", "zone IN ('shared', 'vault', 'attachment')")
    op.create_check_constraint(
        "chk_files_owner_type", "files",
        "owner_type IN ('document', 'announcement', 'task_submission')",
    )
    op.create_check_constraint("chk_files_size_bytes", "files", "size_bytes >= 0")
    op.create_index(
        "idx_files_family_zone_folder_created", "files",
        ["family_id", "zone", "folder_id", sa.text("created_at DESC")],
    )
    op.create_index("idx_files_owner", "files", ["owner_type", "owner_id"])

    # -----------------------------------------------------------------------
    # quotas
    # -----------------------------------------------------------------------
    op.create_table(
        "quotas",
        sa.Column("family_id", UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("plan", sa.String(20), nullable=False, server_default="free"),
        sa.Column("total_bytes", sa.Integer(), nullable=False, server_default="2147483648"),
        sa.Column("used_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_check_constraint("chk_quotas_total_bytes", "quotas", "total_bytes >= 0")
    op.create_check_constraint("chk_quotas_used_bytes", "quotas", "used_bytes >= 0")

    # -----------------------------------------------------------------------
    # vault_email_otps
    # -----------------------------------------------------------------------
    op.create_table(
        "vault_email_otps",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_vault_email_otps_user_expires", "vault_email_otps", ["user_id", sa.text("expires_at DESC")])

    # -----------------------------------------------------------------------
    # vault_sessions
    # -----------------------------------------------------------------------
    op.create_table(
        "vault_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("family_id", UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_vault_sessions_user_family_expires", "vault_sessions",
        ["user_id", "family_id", sa.text("expires_at DESC")],
    )

    # -----------------------------------------------------------------------
    # scenario_templates
    # -----------------------------------------------------------------------
    op.create_table(
        "scenario_templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("definition", JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_scenario_templates_key_version", "scenario_templates", ["key", "version"])

    # -----------------------------------------------------------------------
    # scenario_instances
    # -----------------------------------------------------------------------
    op.create_table(
        "scenario_instances",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("family_id", UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_id", UUID(as_uuid=True), sa.ForeignKey("scenario_templates.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="enabled"),
        sa.Column("config", JSONB(), nullable=False, server_default="{}"),
        sa.Column("enabled_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_check_constraint("chk_scenario_instances_status", "scenario_instances", "status IN ('enabled', 'disabled')")
    op.create_unique_constraint("uq_scenario_instances_family_template", "scenario_instances", ["family_id", "template_id"])

    # -----------------------------------------------------------------------
    # audit_logs
    # -----------------------------------------------------------------------
    op.create_table(
        "audit_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("family_id", UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=True),
        sa.Column("target_id", UUID(as_uuid=True), nullable=True),
        sa.Column("detail", JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_audit_logs_family_created", "audit_logs", ["family_id", sa.text("created_at DESC")])
    op.create_index("idx_audit_logs_action", "audit_logs", ["action"])


def downgrade() -> None:
    # Drop all tables in reverse dependency order
    tables = [
        "audit_logs",
        "scenario_instances",
        "scenario_templates",
        "vault_sessions",
        "vault_email_otps",
        "quotas",
        "files",
        "folders",
        "task_submissions",
        "tasks",
        "announcements",
        "invites",
        "memberships",
        "families",
        "user_identities",
        "users",
    ]
    for table in tables:
        op.drop_table(table)

    op.execute("drop extension if exists pgcrypto")
