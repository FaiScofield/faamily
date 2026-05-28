"""Pydantic schemas for VIP subscription related request/response models."""

from datetime import datetime

from pydantic import BaseModel, Field


class VipSubscribeRequest(BaseModel):
    """Request body for subscribing or upgrading to a VIP plan."""

    tier: str = Field(description="'basic' | 'premium' | 'enterprise'")
    auto_renew: bool = False
    payment_provider: str | None = None
    payment_id: str | None = None


class VipResponse(BaseModel):
    """VIP subscription data returned by API."""

    user_id: str
    tier: str
    started_at: datetime
    expires_at: datetime | None
    auto_renew: bool

    model_config = {"from_attributes": True}


class VipTierInfo(BaseModel):
    """Description of a VIP tier for the catalog."""

    tier: str
    name: str
    description: str
    price_monthly: float
    features: list[str]


class VipCatalogResponse(BaseModel):
    """VIP tier catalog."""

    tiers: list[VipTierInfo]


class VipHistoryRecord(BaseModel):
    """A single record in the VIP subscription history."""

    tier: str
    started_at: datetime
    expires_at: datetime | None
    payment_provider: str | None
    payment_id: str | None

    model_config = {"from_attributes": True}


class VipHistoryResponse(BaseModel):
    """VIP subscription history."""

    records: list[VipHistoryRecord]
