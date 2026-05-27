"""Pydantic schemas for auth-related request/response models."""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


# ---------------------------------------------------------------------------
# Common
# ---------------------------------------------------------------------------


class TokenResponse(BaseModel):
    """JWT token pair returned after successful login."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Request body for refreshing an access token."""

    refresh_token: str


# ---------------------------------------------------------------------------
# Guest Login
# ---------------------------------------------------------------------------


class GuestLoginResponse(BaseModel):
    """Response after guest (anonymous) login."""

    user_id: str
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    is_new: bool = Field(description="Whether a new anonymous user was created")


# ---------------------------------------------------------------------------
# Email Auth
# ---------------------------------------------------------------------------


class EmailRegisterRequest(BaseModel):
    """Request body for email registration."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class EmailLoginRequest(BaseModel):
    """Request body for email login."""

    email: EmailStr
    password: str


class EmailVerifyRequest(BaseModel):
    """Request body for verifying an email with OTP code."""

    email: EmailStr
    code: str = Field(min_length=6, max_length=6)


class EmailSendOtpRequest(BaseModel):
    """Request body for requesting an email OTP."""

    email: EmailStr


# ---------------------------------------------------------------------------
# WeChat Mini Program Auth
# ---------------------------------------------------------------------------


class WechatLoginRequest(BaseModel):
    """Request body for WeChat Mini Program login.

    The frontend exchanges wx.login() code for openid/unionid
    via WeChat server, then sends openid (and optional unionid) here.
    """

    code: str = Field(description="wx.login code, will be exchanged for openid/unionid by backend")
    nickname: str | None = None
    avatar_url: str | None = None


class WechatLoginResponse(BaseModel):
    """Response after WeChat Mini Program login."""

    user_id: str
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    is_new: bool


# ---------------------------------------------------------------------------
# User Profile
# ---------------------------------------------------------------------------


class UserProfile(BaseModel):
    """Public user profile returned by API."""

    user_id: str
    identities: list[dict] = Field(default_factory=list, description="List of bound identities (type, partial identifier)")
    created_at: datetime

    model_config = {"from_attributes": True}
