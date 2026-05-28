"""Audit logging service layer.

Records critical operations (member management, vault access,
file deletion, etc.) into the audit_logs table for compliance
and accountability.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import AuditLog


# Actions that should be audited
AUDIT_ACTIONS = {
    # Membership
    "member.joined",
    "member.removed",
    "member.role_changed",
    "member.ownership_transferred",
    # Invite
    "invite.created",
    "invite.disabled",
    # Family
    "family.created",
    "family.updated",
    "family.deleted",
    # Vault
    "vault.otp_requested",
    "vault.otp_verified",
    "vault.session_created",
    "vault.session_revoked",
    # File
    "file.uploaded",
    "file.deleted",
    # Announcement
    "announcement.created",
    "announcement.updated",
    "announcement.deleted",
}


def write_audit_log(
    db: Session,
    family_id: str,
    actor_user_id: str,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    detail: dict | None = None,
) -> AuditLog:
    """Write an audit log entry.

    Args:
        db: Database session.
        family_id: UUID of the family.
        actor_user_id: UUID of the user performing the action.
        action: Action identifier (e.g. 'member.removed').
        target_type: Optional type of the target object.
        target_id: Optional UUID of the target object.
        detail: Optional additional details as JSON.

    Returns:
        The created AuditLog object.
    """
    log = AuditLog(
        family_id=family_id,
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail or {},
    )
    db.add(log)
    # Flush but don't commit — let the caller's transaction handle it
    db.flush()
    return log


def list_audit_logs(
    db: Session,
    family_id: str,
    action: str | None = None,
    actor_user_id: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[AuditLog], int]:
    """List audit logs for a family.

    Args:
        db: Database session.
        family_id: UUID of the family.
        action: Optional filter by action type.
        actor_user_id: Optional filter by actor.
        offset: Pagination offset.
        limit: Pagination limit.

    Returns:
        Tuple of (logs list, total count).
    """
    query = db.query(AuditLog).filter(AuditLog.family_id == family_id)

    if action:
        query = query.filter(AuditLog.action == action)
    if actor_user_id:
        query = query.filter(AuditLog.actor_user_id == actor_user_id)

    total = query.count()
    logs = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()
    return logs, total
