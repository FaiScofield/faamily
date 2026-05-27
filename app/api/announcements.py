"""Announcement API routes.

Endpoints:
- POST   /families/{family_id}/announcements              — Create announcement
- GET    /families/{family_id}/announcements              — List announcements
- GET    /families/{family_id}/announcements/{id}         — Get announcement
- PUT    /families/{family_id}/announcements/{id}         — Update announcement
- DELETE /families/{family_id}/announcements/{id}         — Soft-delete announcement
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.permissions import require_admin, require_any_role
from app.db import get_db
from app.models import Announcement, Membership, User
from app.schemas.announcement import (
    AnnouncementCreateRequest,
    AnnouncementListResponse,
    AnnouncementResponse,
    AnnouncementUpdateRequest,
)
from app.services.announcement_service import (
    create_announcement,
    get_announcement,
    list_announcements,
    soft_delete_announcement,
    update_announcement,
)

router = APIRouter(prefix="/families/{family_id}/announcements", tags=["announcements"])


@router.post("", response_model=AnnouncementResponse, status_code=status.HTTP_201_CREATED)
def create_new_announcement(
    family_id: str,
    body: AnnouncementCreateRequest,
    membership: Membership = Depends(require_admin),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new announcement (owner or admin only).

    Attachments are limited to 5 files per announcement.
    """
    # Validate attachment count
    if len(body.attachment_ids) > 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 5 attachments allowed per announcement",
        )

    announcement = create_announcement(
        db=db,
        family_id=family_id,
        created_by=str(current_user.id),
        title=body.title,
        content=body.content,
        pinned=body.pinned,
    )

    # TODO: Link attachments to this announcement
    # for file_id in body.attachment_ids:
    #     link_file_to_announcement(db, file_id, announcement.id)

    return announcement


@router.get("", response_model=AnnouncementListResponse)
def list_family_announcements(
    family_id: str,
    membership: Membership = Depends(require_any_role),
    db: Session = Depends(get_db),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
):
    """List announcements in a family.

    Pinned announcements are always returned first, sorted by creation date.
    """
    announcements, total = list_announcements(
        db=db,
        family_id=family_id,
        offset=offset,
        limit=limit,
    )
    return AnnouncementListResponse(announcements=announcements, total=total)


@router.get("/{announcement_id}", response_model=AnnouncementResponse)
def get_announcement_details(
    family_id: str,
    announcement_id: str,
    membership: Membership = Depends(require_any_role),
    db: Session = Depends(get_db),
):
    """Get details of a specific announcement."""
    announcement = get_announcement(db, announcement_id, family_id)
    if not announcement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Announcement not found",
        )
    return announcement


@router.put("/{announcement_id}", response_model=AnnouncementResponse)
def update_announcement_endpoint(
    family_id: str,
    announcement_id: str,
    body: AnnouncementUpdateRequest,
    membership: Membership = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update an announcement (owner or admin only)."""
    announcement = get_announcement(db, announcement_id, family_id)
    if not announcement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Announcement not found",
        )

    announcement = update_announcement(
        db=db,
        announcement=announcement,
        title=body.title,
        content=body.content,
        pinned=body.pinned,
    )
    return announcement


@router.delete("/{announcement_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_announcement_endpoint(
    family_id: str,
    announcement_id: str,
    membership: Membership = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Soft-delete an announcement (owner or admin only)."""
    announcement = get_announcement(db, announcement_id, family_id)
    if not announcement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Announcement not found",
        )

    soft_delete_announcement(db, announcement)
    return None
