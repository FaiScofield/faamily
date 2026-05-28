"""Family business logic service layer.

Handles family creation, membership management, and invitation codes.
"""

import secrets
import string
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import Family, Invite, Membership, Quota, User
from app.services.audit_service import write_audit_log


def generate_invite_code(length: int = 8) -> str:
    """Generate a random alphanumeric invitation code."""
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def create_family(
    db: Session,
    owner: User,
    name: str,
    avatar_url: str | None = None,
) -> Family:
    """Create a new family with the user as owner.

    Automatically creates:
    - Family record
    - Owner membership
    - Default quota (2GB free plan)

    Args:
        db: Database session.
        owner: The user who will own the family.
        name: Family name.
        avatar_url: Optional family avatar URL.

    Returns:
        The newly created Family object.
    """
    # Create family
    family = Family(
        name=name,
        avatar_url=avatar_url,
        owner_user_id=owner.id,
    )
    db.add(family)
    db.flush()

    # Create owner membership
    membership = Membership(
        family_id=family.id,
        user_id=owner.id,
        role="owner",
        status="active",
        display_name=None,
    )
    db.add(membership)

    # Create default quota
    quota = Quota(
        family_id=family.id,
        plan="free",
        total_bytes=2_147_483_648,  # 2GB
        used_bytes=0,
    )
    db.add(quota)

    # Audit: family created
    write_audit_log(
        db, str(family.id), str(owner.id), "family.created",
        target_type="family", target_id=str(family.id),
        detail={"name": name},
    )

    db.commit()
    db.refresh(family)
    return family


def get_user_families(db: Session, user: User) -> list[Family]:
    """Get all families the user is an active member of."""
    memberships = db.query(Membership).filter(
        Membership.user_id == user.id,
        Membership.status == "active",
    ).all()

    family_ids = [m.family_id for m in memberships]
    if not family_ids:
        return []

    families = db.query(Family).filter(Family.id.in_(family_ids)).all()
    return families


def update_family(
    db: Session,
    family: Family,
    name: str | None = None,
    avatar_url: str | None = None,
) -> Family:
    """Update family details.

    Args:
        db: Database session.
        family: Family to update.
        name: New name (optional).
        avatar_url: New avatar URL (optional).

    Returns:
        Updated Family object.
    """
    if name is not None:
        family.name = name
    if avatar_url is not None:
        family.avatar_url = avatar_url

    write_audit_log(
        db, str(family.id), "system", "family.updated",
        target_type="family", target_id=str(family.id),
    )

    db.commit()
    db.refresh(family)
    return family


def delete_family(db: Session, family: Family) -> None:
    """Delete a family and all associated data.

    Args:
        db: Database session.
        family: Family to delete.
    """
    db.delete(family)
    db.commit()


# ---------------------------------------------------------------------------
# Membership Management
# ---------------------------------------------------------------------------


def get_family_members(db: Session, family_id: str) -> list[Membership]:
    """Get all active members of a family."""
    return db.query(Membership).filter(
        Membership.family_id == family_id,
        Membership.status == "active",
    ).all()


def get_membership(db: Session, family_id: str, user_id: str) -> Membership | None:
    """Get a specific membership by family and user."""
    return db.query(Membership).filter(
        Membership.family_id == family_id,
        Membership.user_id == user_id,
    ).first()


def update_member_role(
    db: Session,
    membership: Membership,
    new_role: str,
) -> Membership:
    """Update a member's role.

    Args:
        db: Database session.
        membership: Membership to update.
        new_role: New role (owner/admin/member/child).

    Returns:
        Updated Membership object.
    """
    membership.role = new_role
    db.commit()
    db.refresh(membership)
    return membership


def remove_member(db: Session, membership: Membership) -> None:
    """Soft-remove a member from family.

    Sets status to 'removed' rather than deleting the record
    for audit purposes.

    Args:
        db: Database session.
        membership: Membership to remove.
    """
    membership.status = "removed"

    write_audit_log(
        db, str(membership.family_id), "system", "member.removed",
        target_type="membership", target_id=str(membership.id),
        detail={"user_id": str(membership.user_id), "role": membership.role},
    )

    db.commit()


def transfer_ownership(
    db: Session,
    family: Family,
    current_owner_membership: Membership,
    new_owner_membership: Membership,
) -> None:
    """Transfer family ownership to another member.

    Args:
        db: Database session.
        family: The family.
        current_owner_membership: Current owner's membership.
        new_owner_membership: New owner's membership.
    """
    # Update family owner
    family.owner_user_id = new_owner_membership.user_id

    # Swap roles
    current_owner_membership.role = "admin"
    new_owner_membership.role = "owner"

    write_audit_log(
        db, str(family.id), str(current_owner_membership.user_id), "member.ownership_transferred",
        target_type="membership", target_id=str(new_owner_membership.id),
        detail={
            "from_user_id": str(current_owner_membership.user_id),
            "to_user_id": str(new_owner_membership.user_id),
        },
    )

    db.commit()


# ---------------------------------------------------------------------------
# Invitation Codes
# ---------------------------------------------------------------------------


def create_invite(
    db: Session,
    family: Family,
    created_by: User,
    expires_in_hours: int = 24,
    max_uses: int = 1,
    need_approval: bool = False,
) -> Invite:
    """Create a new invitation code for a family.

    Args:
        db: Database session.
        family: Family to invite to.
        created_by: User creating the invite.
        expires_in_hours: Hours until the invite expires.
        max_uses: Maximum number of times the invite can be used.
        need_approval: Whether join requests require approval.

    Returns:
        The newly created Invite object.
    """
    # Generate unique code
    while True:
        code = generate_invite_code()
        existing = db.query(Invite).filter(Invite.code == code).first()
        if not existing:
            break

    invite = Invite(
        family_id=family.id,
        code=code,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=expires_in_hours),
        max_uses=max_uses,
        used_count=0,
        need_approval=need_approval,
        created_by_user_id=created_by.id,
        disabled_at=None,
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return invite


def get_invite_by_code(db: Session, code: str) -> Invite | None:
    """Get an invite by its code."""
    return db.query(Invite).filter(Invite.code == code).first()


def get_family_invites(db: Session, family_id: str) -> list[Invite]:
    """Get all invites for a family."""
    return db.query(Invite).filter(Invite.family_id == family_id).all()


def is_invite_valid(invite: Invite) -> bool:
    """Check if an invite is valid (not expired, not disabled, has uses remaining).

    Args:
        invite: Invite to check.

    Returns:
        True if the invite can be used.
    """
    if invite.disabled_at is not None:
        return False
    if invite.expires_at < datetime.now(timezone.utc):
        return False
    if invite.used_count >= invite.max_uses:
        return False
    return True


def disable_invite(db: Session, invite: Invite) -> None:
    """Disable an invitation code.

    Args:
        db: Database session.
        invite: Invite to disable.
    """
    invite.disabled_at = datetime.now(timezone.utc)
    db.commit()


def use_invite(db: Session, invite: Invite) -> None:
    """Increment the used_count of an invite.

    Args:
        db: Database session.
        invite: Invite being used.
    """
    invite.used_count += 1
    db.commit()


def join_family_by_invite(
    db: Session,
    invite: Invite,
    user: User,
) -> Membership:
    """Add a user to a family using an invite code.

    Args:
        db: Database session.
        invite: Valid invite code.
        user: User joining the family.

    Returns:
        The new Membership object.

    Raises:
        ValueError: If user is already a member.
    """
    # Check if already a member
    existing = db.query(Membership).filter(
        Membership.family_id == invite.family_id,
        Membership.user_id == user.id,
    ).first()

    if existing:
        if existing.status == "active":
            raise ValueError("User is already a member of this family")
        else:
            # Reactivate removed membership
            existing.status = "active"
            existing.role = "member"
            db.commit()
            db.refresh(existing)
            return existing

    # Create new membership
    membership = Membership(
        family_id=invite.family_id,
        user_id=user.id,
        role="member",
        status="active",
        display_name=None,
    )
    db.add(membership)

    # Increment invite usage
    invite.used_count += 1

    db.commit()
    db.refresh(membership)
    return membership
