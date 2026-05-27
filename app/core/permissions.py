"""Permission checking utilities for family resources.

Provides dependency injectors for FastAPI to enforce:
- Family membership validation
- Role-based access control (owner/admin/member/child)
"""

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db import get_db
from app.models import Family, Membership, User


class PermissionDenied(HTTPException):
    """Raised when user lacks required permissions."""

    def __init__(self, detail: str = "Permission denied"):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


class FamilyNotFound(HTTPException):
    """Raised when family does not exist or user has no access."""

    def __init__(self):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Family not found",
        )


def require_family_member(
    family_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Membership:
    """Verify current user is an active member of the specified family.

    Args:
        family_id: UUID string of the family to check.
        current_user: Authenticated user from JWT.
        db: Database session.

    Returns:
        The Membership object if valid.

    Raises:
        FamilyNotFound: If family doesn't exist or user is not a member.
    """
    # Check family exists
    family = db.query(Family).filter(Family.id == family_id).first()
    if not family:
        raise FamilyNotFound()

    # Check membership
    membership = db.query(Membership).filter(
        Membership.family_id == family_id,
        Membership.user_id == current_user.id,
        Membership.status == "active",
    ).first()

    if not membership:
        raise FamilyNotFound()

    return membership


def require_family_role(
    family_id: str,
    allowed_roles: list[str],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Membership:
    """Verify current user has one of the allowed roles in the family.

    Args:
        family_id: UUID string of the family to check.
        allowed_roles: List of allowed role names (e.g. ['owner', 'admin']).
        current_user: Authenticated user from JWT.
        db: Database session.

    Returns:
        The Membership object if valid.

    Raises:
        FamilyNotFound: If family doesn't exist or user is not a member.
        PermissionDenied: If user lacks required role.
    """
    membership = require_family_member(family_id, current_user, db)

    if membership.role not in allowed_roles:
        raise PermissionDenied(
            f"This action requires one of the following roles: {', '.join(allowed_roles)}"
        )

    return membership


class FamilyPermissionChecker:
    """Factory for creating role-based permission dependencies.

    Usage:
        @router.post("/families/{family_id}/...")
        def some_endpoint(
            membership: Membership = Depends(FamilyPermissionChecker("owner", "admin")),
        ):
            ...
    """

    def __init__(self, *roles: str):
        """Initialize with allowed roles.

        Args:
            roles: One or more role names (owner, admin, member, child).
        """
        self.allowed_roles = list(roles)

    def __call__(
        self,
        family_id: str,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> Membership:
        """Check permission when used as a FastAPI dependency."""
        return require_family_role(family_id, self.allowed_roles, current_user, db)


# Predefined permission checkers for common use cases
require_owner = FamilyPermissionChecker("owner")
require_admin = FamilyPermissionChecker("owner", "admin")
require_member = FamilyPermissionChecker("owner", "admin", "member")
require_any_role = FamilyPermissionChecker("owner", "admin", "member", "child")


def can_manage_member(
    actor_membership: Membership,
    target_membership: Membership,
) -> bool:
    """Check if actor can manage (modify/remove) target member.

    Rules:
    - Owner can manage admin/member/child, but not other owners
    - Admin can manage member/child, but not owners or other admins
    - Member/Child cannot manage anyone

    Args:
        actor_membership: Membership of the user performing the action.
        target_membership: Membership of the user being managed.

    Returns:
        True if actor can manage target.
    """
    actor_role = actor_membership.role
    target_role = target_membership.role

    if actor_role == "owner":
        # Owner can manage anyone except other owners
        return target_role != "owner"
    elif actor_role == "admin":
        # Admin can manage members and children only
        return target_role in ("member", "child")
    else:
        # Members and children cannot manage anyone
        return False


def can_transfer_ownership(
    actor_membership: Membership,
    target_membership: Membership,
) -> bool:
    """Check if actor can transfer ownership to target.

    Only the current owner can transfer ownership to another active member.

    Args:
        actor_membership: Membership of the user performing the action.
        target_membership: Membership of the user receiving ownership.

    Returns:
        True if ownership can be transferred.
    """
    if actor_membership.role != "owner":
        return False
    if target_membership.role not in ("admin", "member"):
        return False
    if target_membership.status != "active":
        return False
    return True
