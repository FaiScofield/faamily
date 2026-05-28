"""VIP subscription business logic service layer."""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import User, VipSubscription


# VIP tier definitions
VIP_TIERS = {
    "free": {
        "name": "免费版",
        "description": "基础功能，满足日常家庭使用",
        "price_monthly": 0,
        "features": ["创建家庭", "基础任务管理", "文档库 2GB"],
    },
    "basic": {
        "name": "基础会员",
        "description": "更多存储空间和功能",
        "price_monthly": 19.9,
        "features": ["创建家庭", "高级任务管理", "文档库 10GB", "保险箱存储", "审计日志"],
    },
    "premium": {
        "name": "高级会员",
        "description": "全部功能，无限制体验",
        "price_monthly": 49.9,
        "features": ["创建家庭", "高级任务管理", "文档库 100GB", "保险箱存储", "审计日志", "预设场景模板", "不限家庭成员"],
    },
    "enterprise": {
        "name": "企业版",
        "description": "为家族定制的高端方案",
        "price_monthly": 99.9,
        "features": ["包含高级会员全部功能", "文档库 1TB", "专属客服", "自定义模板"],
    },
}


def get_vip_tier_info(tier: str) -> dict | None:
    """Get information about a specific VIP tier."""
    return VIP_TIERS.get(tier)


def get_vip_catalog() -> list[dict]:
    """Get the full VIP tier catalog."""
    return [
        {"tier": k, **v}
        for k, v in VIP_TIERS.items()
        if k != "free"  # Exclude free tier from subscription catalog
    ]


def get_user_subscription(db: Session, user_id: str) -> VipSubscription | None:
    """Get the current subscription for a user.

    Free users have no subscription record.

    Args:
        db: Database session.
        user_id: UUID of the user.

    Returns:
        VipSubscription object or None (free tier).
    """
    return db.query(VipSubscription).filter(
        VipSubscription.user_id == user_id,
    ).first()


def get_user_effective_tier(db: Session, user_id: str) -> str:
    """Get the effective VIP tier for a user.

    Returns 'free' if no active subscription.

    Args:
        db: Database session.
        user_id: UUID of the user.

    Returns:
        Tier name: 'free', 'basic', 'premium', or 'enterprise'.
    """
    sub = get_user_subscription(db, user_id)
    if not sub:
        return "free"
    if sub.expires_at and sub.expires_at < datetime.now(timezone.utc):
        return "free"
    return sub.tier


def subscribe_or_upgrade(
    db: Session,
    user: User,
    tier: str,
    auto_renew: bool = False,
    payment_provider: str | None = None,
    payment_id: str | None = None,
) -> VipSubscription:
    """Subscribe to or upgrade a VIP plan for the user.

    Creates a new subscription record if none exists, or updates
    the existing one (only upgrades are allowed — downgrades should
    wait for expiry).

    Args:
        db: Database session.
        user: The user subscribing.
        tier: Target tier ('basic', 'premium', 'enterprise').
        auto_renew: Whether to auto-renew.
        payment_provider: Payment provider name.
        payment_id: Payment transaction ID.

    Returns:
        The VipSubscription object.

    Raises:
        ValueError: If tier is invalid or downgrade attempted.
    """
    if tier not in ("basic", "premium", "enterprise"):
        raise ValueError(f"Invalid VIP tier: {tier}")

    existing = get_user_subscription(db, str(user.id))

    if existing:
        # Check not a downgrade
        tier_order = {"free": 0, "basic": 1, "premium": 2, "enterprise": 3}
        if tier_order.get(tier, 0) < tier_order.get(existing.tier, 0):
            raise ValueError(
                f"Cannot downgrade from '{existing.tier}' to '{tier}'. "
                "Downgrades take effect after the current period expires."
            )

        # Update existing subscription
        existing.tier = tier
        existing.auto_renew = auto_renew
        existing.payment_provider = payment_provider
        existing.payment_id = payment_id
        if tier != existing.tier:
            existing.started_at = datetime.now(timezone.utc)
        # Extend expiry: 30 days from now
        existing.expires_at = datetime.now(timezone.utc) + timedelta(days=30)

        db.commit()
        db.refresh(existing)
        return existing
    else:
        # Create new subscription
        sub = VipSubscription(
            user_id=user.id,
            tier=tier,
            started_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            auto_renew=auto_renew,
            payment_provider=payment_provider,
            payment_id=payment_id,
        )
        db.add(sub)
        db.commit()
        db.refresh(sub)
        return sub


def cancel_subscription(db: Session, user_id: str) -> VipSubscription | None:
    """Cancel auto-renewal for a subscription.

    The subscription remains active until its expiry date.

    Args:
        db: Database session.
        user_id: UUID of the user.

    Returns:
        Updated VipSubscription or None if no subscription exists.
    """
    sub = get_user_subscription(db, user_id)
    if sub:
        sub.auto_renew = False
        db.commit()
        db.refresh(sub)
    return sub


def has_feature_access(db: Session, user_id: str, feature: str) -> bool:
    """Check if a user has access to a specific VIP feature.

    Args:
        db: Database session.
        user_id: UUID of the user.
        feature: Feature name to check.

    Returns:
        True if the user's current tier includes this feature.
    """
    tier = get_user_effective_tier(db, user_id)
    tier_info = VIP_TIERS.get(tier, VIP_TIERS["free"])
    features = set(tier_info["features"])

    # Check this tier's features
    if feature in features:
        return True

    # Check lower tiers (features are cumulative upward)
    tier_order = ["free", "basic", "premium", "enterprise"]
    current_index = tier_order.index(tier) if tier in tier_order else 0

    for i in range(current_index):
        lower_tier = tier_order[i]
        lower_info = VIP_TIERS.get(lower_tier, {})
        if feature in set(lower_info.get("features", [])):
            return True

    return False
