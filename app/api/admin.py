"""Admin dashboard API routes.

All endpoints require admin authentication (defined by ADMIN_USER_IDS in .env).

Endpoints:
- GET /admin/dashboard        — Consolidated dashboard summary
- GET /admin/users            — User registration stats
- GET /admin/online           — Online users
- GET /admin/vip              — VIP distribution
- GET /admin/regions          — Regional distribution
- GET /admin/families         — Family stats
- GET /admin/audit            — Audit log summary
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import require_admin_user
from app.core.config import settings
from app.db import get_db
from app.models import User
from app.services.admin_service import (
    get_audit_summary,
    get_dashboard_summary,
    get_family_stats,
    get_online_users,
    get_region_stats,
    get_user_stats,
    get_vip_stats,
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/dashboard")
def admin_dashboard(
    current_user: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    """Get a consolidated dashboard with all key metrics."""
    return get_dashboard_summary(db, settings.online_timeout_minutes)


@router.get("/users")
def admin_user_stats(
    current_user: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    """Get user registration statistics."""
    return get_user_stats(db)


@router.get("/online")
def admin_online_users(
    current_user: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    """Get online user statistics."""
    return get_online_users(db, settings.online_timeout_minutes)


@router.get("/vip")
def admin_vip_stats(
    current_user: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    """Get VIP distribution statistics."""
    return get_vip_stats(db)


@router.get("/regions")
def admin_region_stats(
    current_user: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    """Get user regional distribution statistics."""
    return get_region_stats(db)


@router.get("/families")
def admin_family_stats(
    current_user: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    """Get family and membership statistics."""
    return get_family_stats(db)


@router.get("/audit")
def admin_audit_summary(
    current_user: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
    days: int = Query(default=7, ge=1, le=90),
):
    """Get audit log summary for the recent period."""
    return get_audit_summary(db, days)
