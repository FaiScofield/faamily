"""Pydantic schemas for announcement-related request/response models."""

from datetime import datetime

from pydantic import BaseModel, Field


class AnnouncementCreateRequest(BaseModel):
    """Request body for creating an announcement."""

    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=5000)
    pinned: bool = False
    attachment_ids: list[str] = Field(default_factory=list, description="File IDs as attachments (max 5)")


class AnnouncementUpdateRequest(BaseModel):
    """Request body for updating an announcement."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, min_length=1, max_length=5000)
    pinned: bool | None = None


class AnnouncementResponse(BaseModel):
    """Announcement data returned by API."""

    announcement_id: str
    family_id: str
    title: str
    content: str
    pinned: bool
    created_by_user_id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AnnouncementListResponse(BaseModel):
    """List of announcements."""

    announcements: list[AnnouncementResponse]
    total: int
