"""VIP subscription API routes.

Endpoints:
- GET    /vip/catalog         — List available VIP tier plans
- GET    /vip/status          — Get current user's VIP status
- POST   /vip/subscribe       — Subscribe or upgrade to a VIP plan
- POST   /vip/cancel          — Cancel auto-renewal
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db import get_db
from app.models import User
from app.schemas.vip import (
    VipCatalogResponse,
    VipHistoryResponse,
    VipResponse,
    VipSubscribeRequest,
    VipTierInfo,
)
from app.services.vip_service import (
    cancel_subscription,
    get_user_effective_tier,
    get_user_subscription,
    get_vip_catalog,
    subscribe_or_upgrade,
)

router = APIRouter(prefix="/vip", tags=["vip"])


@router.get("/catalog", response_model=VipCatalogResponse)
def list_vip_catalog():
    """List available VIP tier plans with pricing and features."""
    catalog = get_vip_catalog()
    return VipCatalogResponse(
        tiers=[VipTierInfo(**t) for t in catalog]
    )


@router.get("/status")
def get_vip_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the current user's VIP subscription status."""
    tier = get_user_effective_tier(db, str(current_user.id))
    sub = get_user_subscription(db, str(current_user.id))

    result = {
        "user_id": str(current_user.id),
        "tier": tier,
    }

    if sub:
        result.update({
            "started_at": sub.started_at.isoformat(),
            "expires_at": sub.expires_at.isoformat() if sub.expires_at else None,
            "auto_renew": sub.auto_renew,
        })

    return result


@router.post("/subscribe", response_model=VipResponse)
def subscribe_vip(
    body: VipSubscribeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Subscribe to or upgrade a VIP plan.

    Only upgrades are allowed. Downgrades take effect after
    the current billing period expires.
    """
    try:
        sub = subscribe_or_upgrade(
            db=db,
            user=current_user,
            tier=body.tier,
            auto_renew=body.auto_renew,
            payment_provider=body.payment_provider,
            payment_id=body.payment_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return sub


@router.post("/cancel")
def cancel_vip_auto_renew(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cancel auto-renewal for the current VIP subscription.

    The subscription remains active until its expiry date.
    """
    sub = cancel_subscription(db, str(current_user.id))
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active subscription found",
        )

    return {
        "detail": "Auto-renewal cancelled",
        "tier": sub.tier,
        "expires_at": sub.expires_at.isoformat() if sub.expires_at else None,
    }
