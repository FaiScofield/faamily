"""Family API routes.

Endpoints:
- POST   /families              — Create a new family
- GET    /families              — List current user's families
- GET    /families/{id}         — Get family details
- PUT    /families/{id}         — Update family
- DELETE /families/{id}         — Delete family
- GET    /families/{id}/members             — List family members
- PUT    /families/{id}/members/{user_id}/role        — Update member role
- PUT    /families/{id}/members/{user_id}/permissions — Update member permissions
- DELETE /families/{id}/members/{user_id}             — Remove member
- POST   /families/{id}/invites — Create invite code
- GET    /families/{id}/invites — List invite codes
- DELETE /families/{id}/invites/{invite_id}    — Disable invite code
- POST   /families/join         — Join family by invite code
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.permissions import (
    FamilyNotFound,
    PermissionDenied,
    can_manage_member,
    can_transfer_ownership,
    require_admin,
    require_any_role,
    require_owner,
    set_permission,
)
from app.db import get_db
from app.models import Family, Membership, User
from app.schemas.family import (
    FamilyCreateRequest,
    FamilyListResponse,
    FamilyResponse,
    FamilyUpdateRequest,
    InviteCreateRequest,
    InviteListResponse,
    InviteResponse,
    JoinByInviteRequest,
    JoinByInviteResponse,
    MemberListResponse,
    MemberPermissionsUpdateRequest,
    MemberRemoveRequest,
    MemberResponse,
    MemberRoleUpdateRequest,
)
from app.services.family_service import (
    create_family,
    create_invite,
    disable_invite,
    get_family_invites,
    get_invite_by_code,
    get_membership,
    get_user_families,
    is_invite_valid,
    join_family_by_invite,
    remove_member,
    transfer_ownership,
    update_family,
    update_member_role,
)

router = APIRouter(prefix="/families", tags=["families"])


# ---------------------------------------------------------------------------
# Family CRUD
# ---------------------------------------------------------------------------


@router.post("", response_model=FamilyResponse, status_code=status.HTTP_201_CREATED)
def create_new_family(
    body: FamilyCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new family. The current user becomes the owner."""
    family = create_family(
        db=db,
        owner=current_user,
        name=body.name,
        avatar_url=body.avatar_url,
    )
    return family


@router.get("", response_model=FamilyListResponse)
def list_my_families(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all families the current user is a member of."""
    families = get_user_families(db, current_user)
    return FamilyListResponse(families=families)


@router.get("/{family_id}", response_model=FamilyResponse)
def get_family_details(
    family_id: str,
    membership: Membership = Depends(require_any_role),
    db: Session = Depends(get_db),
):
    """Get details of a specific family."""
    family = db.query(Family).filter(Family.id == family_id).first()
    if not family:
        raise FamilyNotFound()
    return family


@router.put("/{family_id}", response_model=FamilyResponse)
def update_family_details(
    family_id: str,
    body: FamilyUpdateRequest,
    membership: Membership = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update family details (owner or admin only)."""
    family = db.query(Family).filter(Family.id == family_id).first()
    if not family:
        raise FamilyNotFound()

    family = update_family(
        db=db,
        family=family,
        name=body.name,
        avatar_url=body.avatar_url,
    )
    return family


@router.delete("/{family_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_family_endpoint(
    family_id: str,
    membership: Membership = Depends(require_owner),
    db: Session = Depends(get_db),
):
    """Delete a family (owner only)."""
    family = db.query(Family).filter(Family.id == family_id).first()
    if not family:
        raise FamilyNotFound()

    delete_family(db=db, family=family)
    return None


# ---------------------------------------------------------------------------
# Membership Management
# ---------------------------------------------------------------------------


@router.get("/{family_id}/members", response_model=MemberListResponse)
def list_family_members(
    family_id: str,
    membership: Membership = Depends(require_any_role),
    db: Session = Depends(get_db),
):
    """List all active members of a family."""
    members = get_family_members(db, family_id)
    return MemberListResponse(members=members)


@router.put("/{family_id}/members/{user_id}/role", response_model=MemberResponse)
def update_member_role_endpoint(
    family_id: str,
    user_id: str,
    body: MemberRoleUpdateRequest,
    actor_membership: Membership = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update a member's role (owner or admin only)."""
    # Cannot change own role through this endpoint
    if str(actor_membership.user_id) == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change your own role. Use ownership transfer instead.",
        )

    target_membership = get_membership(db, family_id, user_id)
    if not target_membership or target_membership.status != "active":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found",
        )

    # Check if actor can manage target
    if not can_manage_member(actor_membership, target_membership):
        raise PermissionDenied("You cannot manage this member's role")

    # Special handling for ownership transfer
    if body.role == "owner":
        if not can_transfer_ownership(actor_membership, target_membership):
            raise PermissionDenied("Cannot transfer ownership to this member")

        family = db.query(Family).filter(Family.id == family_id).first()
        transfer_ownership(
            db=db,
            family=family,
            current_owner_membership=actor_membership,
            new_owner_membership=target_membership,
        )
        db.refresh(target_membership)
        return target_membership

    # Regular role update
    target_membership = update_member_role(db, target_membership, body.role)
    return target_membership


@router.put("/{family_id}/members/{user_id}/permissions", response_model=MemberResponse)
def update_member_permissions_endpoint(
    family_id: str,
    user_id: str,
    body: MemberPermissionsUpdateRequest,
    actor_membership: Membership = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update a member's permission flags (owner or admin only).

    Used for child-like restrictions — e.g. {'restricted': true} limits
    the member's access to certain family features.
    """
    target_membership = get_membership(db, family_id, user_id)
    if not target_membership or target_membership.status != "active":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found",
        )

    # Check if actor can manage target
    if not can_manage_member(actor_membership, target_membership):
        raise PermissionDenied("You cannot modify this member's permissions")

    # Update permission flags
    for flag, value in body.permissions.items():
        set_permission(target_membership, flag, value)

    db.commit()
    db.refresh(target_membership)
    return target_membership


@router.delete("/{family_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member_endpoint(
    family_id: str,
    user_id: str,
    actor_membership: Membership = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Remove a member from the family (owner or admin only).

    Owners can remove anyone except other owners.
    Admins can only remove members.
    """
    # Cannot remove self through this endpoint
    if str(actor_membership.user_id) == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove yourself. Leave the family instead.",
        )

    target_membership = get_membership(db, family_id, user_id)
    if not target_membership or target_membership.status != "active":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found",
        )

    # Check if actor can manage target
    if not can_manage_member(actor_membership, target_membership):
        raise PermissionDenied("You cannot remove this member")

    remove_member(db, target_membership)
    return None


# ---------------------------------------------------------------------------
# Invitation Codes
# ---------------------------------------------------------------------------


@router.post("/{family_id}/invites", response_model=InviteResponse, status_code=status.HTTP_201_CREATED)
def create_invite_endpoint(
    family_id: str,
    body: InviteCreateRequest,
    membership: Membership = Depends(require_admin),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create an invitation code for the family (owner or admin only)."""
    family = db.query(Family).filter(Family.id == family_id).first()
    if not family:
        raise FamilyNotFound()

    invite = create_invite(
        db=db,
        family=family,
        created_by=current_user,
        expires_in_hours=body.expires_in_hours,
        max_uses=body.max_uses,
        need_approval=body.need_approval,
    )
    return invite


@router.get("/{family_id}/invites", response_model=InviteListResponse)
def list_invites_endpoint(
    family_id: str,
    membership: Membership = Depends(require_any_role),
    db: Session = Depends(get_db),
):
    """List all invitation codes for the family."""
    invites = get_family_invites(db, family_id)
    return InviteListResponse(invites=invites)


@router.delete("/{family_id}/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
def disable_invite_endpoint(
    family_id: str,
    invite_id: str,
    membership: Membership = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Disable an invitation code (owner or admin only)."""
    from app.models import Invite

    invite = db.query(Invite).filter(
        Invite.id == invite_id,
        Invite.family_id == family_id,
    ).first()

    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invite not found",
        )

    disable_invite(db, invite)
    return None


# ---------------------------------------------------------------------------
# Join Family
# ---------------------------------------------------------------------------


@router.post("/join", response_model=JoinByInviteResponse)
def join_family_endpoint(
    body: JoinByInviteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Join a family using an invitation code."""
    invite = get_invite_by_code(db, body.code)
    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid invite code",
        )

    if not is_invite_valid(invite):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invite code has expired or reached usage limit",
        )

    if invite.need_approval:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Invite requires approval (not implemented yet)",
        )

    try:
        membership = join_family_by_invite(db, invite, current_user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

    return JoinByInviteResponse(
        family_id=str(invite.family_id),
        membership_id=str(membership.id),
        role=membership.role,
    )
