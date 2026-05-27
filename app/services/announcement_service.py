"""Announcement business logic service layer."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Announcement


def create_announcement(
    db: Session,
    family_id: str,
    created_by: str,
    title: str,
    content: str,
    pinned: bool = False,
) -> Announcement:
    """Create a new announcement.

    Args:
        db: Database session.
        family_id: UUID of the family.
        created_by: UUID of the creating user.
        title: Announcement title.
        content: Announcement content.
        pinned: Whether to pin the announcement.

    Returns:
        The newly created Announcement object.
    """
    announcement = Announcement(
        family_id=family_id,
        title=title,
        content=content,
        pinned=pinned,
        created_by_user_id=created_by,
    )
    db.add(announcement)
    db.commit()
    db.refresh(announcement)
    return announcement


def get_announcement(db: Session, announcement_id: str, family_id: str) -> Announcement | None:
    """Get a single announcement by ID and family (ensures data isolation)."""
    return db.query(Announcement).filter(
        Announcement.id == announcement_id,
        Announcement.family_id == family_id,
        Announcement.deleted_at.is_(None),
    ).first()


def list_announcements(
    db: Session,
    family_id: str,
    include_pinned: bool = True,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[Announcement], int]:
    """List announcements with pinned ones first.

    Args:
        db: Database session.
        family_id: UUID of the family.
        include_pinned: Whether to include pinned announcements.
        offset: Pagination offset.
        limit: Pagination limit.

    Returns:
        Tuple of (announcements list, total count).
    """
    query = db.query(Announcement).filter(
        Announcement.family_id == family_id,
        Announcement.deleted_at.is_(None),
    )

    if not include_pinned:
        query = query.filter(Announcement.pinned.is_(False))

    total = query.count()

    # Pinned first, then by creation date
    announcements = query.order_by(
        Announcement.pinned.desc(),
        Announcement.created_at.desc(),
    ).offset(offset).limit(limit).all()

    return announcements, total


def update_announcement(
    db: Session,
    announcement: Announcement,
    title: str | None = None,
    content: str | None = None,
    pinned: bool | None = None,
) -> Announcement:
    """Update announcement fields.

    Only non-None fields will be updated.

    Args:
        db: Database session.
        announcement: Announcement to update.
        title: New title.
        content: New content.
        pinned: New pinned status.

    Returns:
        Updated Announcement object.
    """
    if title is not None:
        announcement.title = title
    if content is not None:
        announcement.content = content
    if pinned is not None:
        announcement.pinned = pinned

    db.commit()
    db.refresh(announcement)
    return announcement


def soft_delete_announcement(db: Session, announcement: Announcement) -> None:
    """Soft-delete an announcement by setting deleted_at."""
    announcement.deleted_at = datetime.now(timezone.utc)
    db.commit()
