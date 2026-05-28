"""Admin dashboard statistics service.

Provides aggregated statistics for the admin dashboard:
- User registration counts (total, daily, weekly, monthly)
- Online users count
- VIP distribution
- Regional distribution
- Family and membership stats
- Audit log summary
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.models import AuditLog, Family, Membership, User, VipSubscription


def get_user_stats(db: Session) -> dict:
    """Get user registration statistics.

    Returns:
        Dict with total_users, users_today, users_this_week, users_this_month.
    """
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    total = db.query(func.count(User.id)).scalar() or 0
    today_count = db.query(func.count(User.id)).filter(
        User.created_at >= today_start
    ).scalar() or 0
    week_count = db.query(func.count(User.id)).filter(
        User.created_at >= today_start - timedelta(days=7)
    ).scalar() or 0
    month_count = db.query(func.count(User.id)).filter(
        User.created_at >= today_start - timedelta(days=30)
    ).scalar() or 0

    return {
        "total_users": total,
        "users_today": today_count,
        "users_this_week": week_count,
        "users_this_month": month_count,
    }


def get_online_users(db: Session, timeout_minutes: int = 15) -> dict:
    """Get online user statistics.

    A user is considered "online" if last_activity_at is within
    the timeout window.

    Args:
        db: Database session.
        timeout_minutes: Inactivity timeout in minutes.

    Returns:
        Dict with count and list of online user IDs.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)

    online_users = db.query(User).filter(
        User.last_activity_at >= cutoff,
        User.status == 0,
    ).all()

    return {
        "online_count": len(online_users),
        "online_user_ids": [str(u.id) for u in online_users],
    }


def get_vip_stats(db: Session) -> dict:
    """Get VIP distribution statistics.

    Returns:
        Dict with total_vip_count and breakdown by tier.
    """
    total_active_vip = db.query(func.count(VipSubscription.user_id)).filter(
        VipSubscription.expires_at >= datetime.now(timezone.utc),
    ).scalar() or 0

    # Count by tier
    tier_counts = {}
    for tier in ("basic", "premium", "enterprise"):
        count = db.query(func.count(VipSubscription.user_id)).filter(
            VipSubscription.tier == tier,
            VipSubscription.expires_at >= datetime.now(timezone.utc),
        ).scalar() or 0
        tier_counts[tier] = count

    return {
        "total_active_vip": total_active_vip,
        "by_tier": tier_counts,
    }


def get_region_stats(db: Session) -> dict:
    """Get user regional distribution statistics.

    Uses the region field on User model.
    Returns top regions with user counts.

    Returns:
        Dict with total_regions and regions list.
    """
    results = db.query(
        User.region,
        func.count(User.id).label("count"),
    ).filter(
        User.region.isnot(None),
        User.region != "",
    ).group_by(User.region).order_by(
        text("count DESC")
    ).limit(50).all()

    regions = [
        {"region": row[0], "user_count": row[1]}
        for row in results
    ]

    # Count users without region
    no_region = db.query(func.count(User.id)).filter(
        (User.region.is_(None)) | (User.region == ""),
    ).scalar() or 0

    return {
        "total_regions": len(regions),
        "regions": regions,
        "users_without_region": no_region,
    }


def get_family_stats(db: Session) -> dict:
    """Get family and membership statistics.

    Returns:
        Dict with family counts, average members per family, etc.
    """
    total_families = db.query(func.count(Family.id)).scalar() or 0
    total_memberships = db.query(func.count(Membership.id)).filter(
        Membership.status == "active",
    ).scalar() or 0

    # Average members per family
    avg_members = round(total_memberships / total_families, 1) if total_families > 0 else 0

    # Role distribution
    role_counts = {}
    for role in ("owner", "admin", "member"):
        count = db.query(func.count(Membership.id)).filter(
            Membership.role == role,
            Membership.status == "active",
        ).scalar() or 0
        role_counts[role] = count

    return {
        "total_families": total_families,
        "total_active_memberships": total_memberships,
        "avg_members_per_family": avg_members,
        "by_role": role_counts,
    }


def get_audit_summary(db: Session, days: int = 7) -> dict:
    """Get audit log summary for the recent period.

    Args:
        db: Database session.
        days: Number of days to look back.

    Returns:
        Dict with total_entries and breakdown by action type.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    total = db.query(func.count(AuditLog.id)).filter(
        AuditLog.created_at >= cutoff,
    ).scalar() or 0

    # Top 10 action types
    action_counts = db.query(
        AuditLog.action,
        func.count(AuditLog.id).label("count"),
    ).filter(
        AuditLog.created_at >= cutoff,
    ).group_by(AuditLog.action).order_by(
        text("count DESC")
    ).limit(10).all()

    return {
        "days": days,
        "total_entries": total,
        "top_actions": [
            {"action": row[0], "count": row[1]}
            for row in action_counts
        ],
    }


def get_dashboard_summary(db: Session, online_timeout_minutes: int = 15) -> dict:
    """Get a consolidated dashboard summary with all key metrics.

    Args:
        db: Database session.
        online_timeout_minutes: Inactivity timeout for online tracking.

    Returns:
        Comprehensive dashboard data dict.
    """
    user_stats = get_user_stats(db)
    online_stats = get_online_users(db, online_timeout_minutes)
    vip_stats = get_vip_stats(db)
    family_stats = get_family_stats(db)

    return {
        "users": user_stats,
        "online": online_stats,
        "vip": vip_stats,
        "families": family_stats,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
