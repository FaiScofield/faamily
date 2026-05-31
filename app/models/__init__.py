"""SQLAlchemy ORM models for the Family Butler application.

All models use a declarative base with UUID primary keys and
timestamptz columns (created_at / updated_at).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    CheckConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.types import GUID


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    type_annotation_map = {
        dict: JSONB,
    }


class TimestampMixin:
    """Mixin that provides created_at and updated_at columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# ---------------------------------------------------------------------------
# User & Identity
# ---------------------------------------------------------------------------


class User(TimestampMixin, Base):
    """Core user entity."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4,
    )
    status: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="0=active, 1=disabled",
    )
    region: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Province/region for geographic stats, populated from identity extra",
    )
    last_activity_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last request timestamp for online tracking",
    )

    # relationships
    identities: Mapped[list["UserIdentity"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    memberships: Mapped[list["Membership"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    families_owned: Mapped[list["Family"]] = relationship(back_populates="owner", foreign_keys="[Family.owner_user_id]")
    tasks_created: Mapped[list["Task"]] = relationship(back_populates="created_by", foreign_keys="[Task.created_by_user_id]")
    announcements: Mapped[list["Announcement"]] = relationship(back_populates="created_by", foreign_keys="[Announcement.created_by_user_id]")

    __table_args__ = (
        Index("idx_users_status", "status"),
        Index("idx_users_region", "region"),
        Index("idx_users_last_activity", "last_activity_at"),
    )


class UserIdentity(TimestampMixin, Base):
    """Stores login identities bound to a user (wechat / phone / email)."""

    __tablename__ = "user_identities"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="'wechat' | 'phone' | 'email'",
    )
    identifier: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    provider: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    extra: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        server_default="{}",
        nullable=False,
    )

    # relationships
    user: Mapped["User"] = relationship(back_populates="identities")

    __table_args__ = (
        CheckConstraint("type IN ('wechat', 'phone', 'email')", name="chk_user_identities_type"),
        UniqueConstraint("type", "identifier", name="uq_user_identities_type_identifier"),
        Index("idx_user_identities_user_id", "user_id"),
        Index("idx_user_identities_type", "type"),
    )


# ---------------------------------------------------------------------------
# Family & Membership
# ---------------------------------------------------------------------------


class Family(TimestampMixin, Base):
    """A family group."""

    __tablename__ = "families"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("users.id"),
        nullable=False,
    )

    # relationships
    owner: Mapped["User"] = relationship(back_populates="families_owned", foreign_keys=[owner_user_id])
    memberships: Mapped[list["Membership"]] = relationship(back_populates="family", cascade="all, delete-orphan")
    invites: Mapped[list["Invite"]] = relationship(back_populates="family", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_families_owner_user_id", "owner_user_id"),
    )


class Membership(TimestampMixin, Base):
    """Maps a user into a family with a specific role and optional restrictions."""

    __tablename__ = "memberships"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="'owner' | 'admin' | 'member'",
    )
    permissions: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        server_default="{}",
        nullable=False,
        comment="Flag-based permissions, e.g. {'restricted': true} for limited access",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        comment="'active' | 'pending' | 'removed'",
    )
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # relationships
    family: Mapped["Family"] = relationship(back_populates="memberships")
    user: Mapped["User"] = relationship(back_populates="memberships")

    __table_args__ = (
        CheckConstraint("role IN ('owner', 'admin', 'member')", name="chk_memberships_role"),
        CheckConstraint("status IN ('active', 'pending', 'removed')", name="chk_memberships_status"),
        UniqueConstraint("family_id", "user_id", name="uq_memberships_family_user"),
        Index("idx_memberships_family_role", "family_id", "role"),
        Index("idx_memberships_user_id", "user_id"),
    )


# ---------------------------------------------------------------------------
# Invite
# ---------------------------------------------------------------------------


class Invite(TimestampMixin, Base):
    """Invitation code for joining a family."""

    __tablename__ = "invites"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    need_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("users.id"),
        nullable=False,
    )
    disabled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # relationships
    family: Mapped["Family"] = relationship(back_populates="invites")

    __table_args__ = (
        CheckConstraint("max_uses >= 1", name="chk_invites_max_uses"),
        CheckConstraint("used_count >= 0", name="chk_invites_used_count"),
        Index("idx_invites_family_expires", "family_id", "expires_at"),
    )


# ---------------------------------------------------------------------------
# Announcement
# ---------------------------------------------------------------------------


class Announcement(TimestampMixin, Base):
    """Family announcement with optional pinning and soft delete."""

    __tablename__ = "announcements"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("users.id"),
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # relationships
    created_by: Mapped["User"] = relationship(back_populates="announcements", foreign_keys=[created_by_user_id])

    __table_args__ = (
        Index("idx_announcements_family_created", "family_id", "created_at"),
        Index("idx_announcements_family_pinned", "family_id", "pinned"),
    )


# ---------------------------------------------------------------------------
# Task & Submission
# ---------------------------------------------------------------------------


class Task(TimestampMixin, Base):
    """Family task with status machine and soft delete."""

    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("users.id"),
        nullable=False,
    )
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("users.id"),
        nullable=True,
    )
    reviewer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("users.id"),
        nullable=True,
    )
    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        comment="'pending' | 'in_progress' | 'submitted' | 'done' | 'rejected'",
    )
    repeat_rule: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # relationships
    created_by: Mapped["User"] = relationship(back_populates="tasks_created", foreign_keys=[created_by_user_id])
    submissions: Mapped[list["TaskSubmission"]] = relationship(back_populates="task", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'in_progress', 'submitted', 'done', 'rejected')",
            name="chk_tasks_status",
        ),
        Index("idx_tasks_family_status_due", "family_id", "status", "due_at"),
        Index("idx_tasks_family_assignee_status", "family_id", "assignee_user_id", "status"),
        Index("idx_tasks_family_created", "family_id", "created_at"),
    )


class TaskSubmission(TimestampMixin, Base):
    """Submission record when an assignee completes a task."""

    __tablename__ = "task_submissions"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    submitted_by_user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("users.id"),
        nullable=False,
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="submitted",
        comment="'submitted' | 'approved' | 'rejected'",
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # relationships
    task: Mapped["Task"] = relationship(back_populates="submissions")

    __table_args__ = (
        CheckConstraint(
            "status IN ('submitted', 'approved', 'rejected')",
            name="chk_task_submissions_status",
        ),
        Index("idx_task_submissions_task_created", "task_id", "created_at"),
    )


# ---------------------------------------------------------------------------
# Folder & File
# ---------------------------------------------------------------------------


class Folder(TimestampMixin, Base):
    """Folder in the family document library (shared or vault zone)."""

    __tablename__ = "folders"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
    )
    zone: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="'shared' | 'vault'",
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("folders.id", ondelete="CASCADE"),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint("zone IN ('shared', 'vault')", name="chk_folders_zone"),
        Index(
            "uq_folders_family_zone_parent_name",
            "family_id",
            "zone",
            "parent_id",
            "name",
            unique=True,
        ),
        Index("idx_folders_family_zone", "family_id", "zone"),
    )


class File(TimestampMixin, Base):
    """Unified file metadata (documents, attachments, credentials)."""

    __tablename__ = "files"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
    )
    zone: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="'shared' | 'vault' | 'attachment'",
    )
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("folders.id", ondelete="SET NULL"),
        nullable=True,
    )
    owner_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="'document' | 'announcement' | 'task_submission'",
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        nullable=True,
    )
    uploader_user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("users.id"),
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    checksum: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint("zone IN ('shared', 'vault', 'attachment')", name="chk_files_zone"),
        CheckConstraint(
            "owner_type IN ('document', 'announcement', 'task_submission')",
            name="chk_files_owner_type",
        ),
        CheckConstraint("size_bytes >= 0", name="chk_files_size_bytes"),
        Index("idx_files_family_zone_folder_created", "family_id", "zone", "folder_id", "created_at"),
        Index("idx_files_owner", "owner_type", "owner_id"),
    )


# ---------------------------------------------------------------------------
# Quota
# ---------------------------------------------------------------------------


class Quota(TimestampMixin, Base):
    """Storage quota per family."""

    __tablename__ = "quotas"

    family_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("families.id", ondelete="CASCADE"),
        primary_key=True,
    )
    plan: Mapped[str] = mapped_column(String(20), nullable=False, default="free")
    total_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=2_147_483_648)
    used_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    __table_args__ = (
        CheckConstraint("total_bytes >= 0", name="chk_quotas_total_bytes"),
        CheckConstraint("used_bytes >= 0", name="chk_quotas_used_bytes"),
    )


# ---------------------------------------------------------------------------
# Account Email OTP
# ---------------------------------------------------------------------------


class EmailVerificationOtp(Base):
    """One-time password for account email verification."""

    __tablename__ = "email_verification_otps"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(Text, nullable=False)
    code_hash: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_email_verification_otps_email_expires", "email", "expires_at"),
    )


# ---------------------------------------------------------------------------
# Vault (OTP & Session)
# ---------------------------------------------------------------------------


class VaultEmailOtp(TimestampMixin, Base):
    """One-time password for vault access verification."""

    __tablename__ = "vault_email_otps"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(Text, nullable=False)
    code_hash: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        Index("idx_vault_email_otps_user_expires", "user_id", "expires_at"),
    )


class VaultSession(TimestampMixin, Base):
    """Short-lived session granted after successful vault OTP verification."""

    __tablename__ = "vault_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
    )
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        Index("idx_vault_sessions_user_family_expires", "user_id", "family_id", "expires_at"),
    )


# ---------------------------------------------------------------------------
# Scenario (Template & Instance)
# ---------------------------------------------------------------------------


class ScenarioTemplate(TimestampMixin, Base):
    """Predefined scenario template (e.g. child learning, elder care)."""

    __tablename__ = "scenario_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4,
    )
    key: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    definition: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        server_default="{}",
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("key", "version", name="uq_scenario_templates_key_version"),
    )


class ScenarioInstance(TimestampMixin, Base):
    """A family's enabled scenario instance."""

    __tablename__ = "scenario_instances"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("scenario_templates.id"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="enabled",
        comment="'enabled' | 'disabled'",
    )
    config: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        server_default="{}",
        nullable=False,
    )
    enabled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint("status IN ('enabled', 'disabled')", name="chk_scenario_instances_status"),
        UniqueConstraint("family_id", "template_id", name="uq_scenario_instances_family_template"),
    )


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------


class AuditLog(Base):
    """Immutable audit log for critical operations."""

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("users.id"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        nullable=True,
    )
    detail: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        server_default="{}",
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_audit_logs_family_created", "family_id", "created_at"),
        Index("idx_audit_logs_action", "action"),
    )


# ---------------------------------------------------------------------------
# VIP Subscription
# ---------------------------------------------------------------------------


class VipSubscription(Base):
    """User VIP subscription record.

    Supports multiple tiers: free (default), basic, premium, enterprise.
    Free users have no subscription record — a record is created upon first upgrade.
    """

    __tablename__ = "vip_subscriptions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tier: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="free",
        comment="'free' | 'basic' | 'premium' | 'enterprise'",
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Null means no expiry (permanent or free tier)",
    )
    auto_renew: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    payment_provider: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    payment_id: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint("tier IN ('free', 'basic', 'premium', 'enterprise')", name="chk_vip_subscriptions_tier"),
        Index("idx_vip_subscriptions_tier", "tier"),
    )
