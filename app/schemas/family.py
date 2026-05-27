"""Pydantic schemas for family-related request/response models."""

from datetime import datetime

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Family
# ---------------------------------------------------------------------------


class FamilyCreateRequest(BaseModel):
    """Request body for creating a new family."""

    name: str = Field(min_length=1, max_length=100)
    avatar_url: str | None = None


class FamilyUpdateRequest(BaseModel):
    """Request body for updating a family."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    avatar_url: str | None = None


class FamilyResponse(BaseModel):
    """Family data returned by API."""

    family_id: str
    name: str
    avatar_url: str | None
    owner_user_id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FamilyListResponse(BaseModel):
    """List of families the current user belongs to."""

    families: list[FamilyResponse]


# ---------------------------------------------------------------------------
# Membership
# ---------------------------------------------------------------------------


class MemberResponse(BaseModel):
    """Member data returned by API."""

    membership_id: str
    user_id: str
    role: str = Field(description="owner | admin | member | child")
    status: str = Field(description="active | pending | removed")
    display_name: str | None
    joined_at: datetime

    model_config = {"from_attributes": True}


class MemberListResponse(BaseModel):
    """List of members in a family."""

    members: list[MemberResponse]


class MemberRoleUpdateRequest(BaseModel):
    """Request body for updating a member's role."""

    role: str = Field(description="owner | admin | member | child")


class MemberRemoveRequest(BaseModel):
    """Request body for removing a member from family."""

    user_id: str


# ---------------------------------------------------------------------------
# Invite
# ---------------------------------------------------------------------------


class InviteCreateRequest(BaseModel):
    """Request body for creating an invitation code."""

    expires_in_hours: int = Field(default=24, ge=1, le=168)
    max_uses: int = Field(default=1, ge=1, le=100)
    need_approval: bool = False


class InviteResponse(BaseModel):
    """Invitation code data returned by API."""

    invite_id: str
    code: str
    expires_at: datetime
    max_uses: int
    used_count: int
    need_approval: bool
    disabled_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class InviteListResponse(BaseModel):
    """List of invitation codes for a family."""

    invites: list[InviteResponse]


class JoinByInviteRequest(BaseModel):
    """Request body for joining a family by invite code."""

    code: str = Field(min_length=6, max_length=20)


class JoinByInviteResponse(BaseModel):
    """Response after successfully joining a family."""

    family_id: str
    membership_id: str
    role: str
