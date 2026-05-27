"""Authentication API routes.

Endpoints:
- POST /auth/guest        — Anonymous guest login
- POST /auth/email/register — Email + password registration
- POST /auth/email/login    — Email + password login
- POST /auth/email/verify   — Verify email with OTP code
- POST /auth/email/send-otp — Request email OTP
- POST /auth/wechat/login   — WeChat Mini Program login
- POST /auth/refresh        — Refresh access token
- GET  /auth/me              — Get current user profile
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.db import get_db
from app.models import User
from app.schemas import (
    EmailLoginRequest,
    EmailRegisterRequest,
    EmailSendOtpRequest,
    EmailVerifyRequest,
    GuestLoginResponse,
    RefreshRequest,
    TokenResponse,
    WechatLoginRequest,
    WechatLoginResponse,
)
from app.services.auth_service import (
    bind_identity_to_user,
    create_anonymous_user,
    get_or_create_user_by_identity,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Guest Login
# ---------------------------------------------------------------------------


@router.post("/guest", response_model=GuestLoginResponse)
def guest_login(db: Session = Depends(get_db)):
    """Create an anonymous guest user and return tokens.

    The guest user can later bind a real identity (email, phone, wechat)
    to upgrade to a full account.
    """
    user = create_anonymous_user(db)
    access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))
    return GuestLoginResponse(
        user_id=str(user.id),
        access_token=access_token,
        refresh_token=refresh_token,
        is_new=True,
    )


# ---------------------------------------------------------------------------
# Email Registration
# ---------------------------------------------------------------------------


@router.post("/email/register", response_model=TokenResponse)
def email_register(body: EmailRegisterRequest, db: Session = Depends(get_db)):
    """Register a new user with email and password.

    The email identity is created but not verified until the user
    completes the OTP verification flow.
    """
    from app.services.auth_service import get_or_create_user_by_identity

    # Check if email is already registered
    from app.models import UserIdentity

    existing = db.query(UserIdentity).filter(
        UserIdentity.type == "email",
        UserIdentity.identifier == body.email,
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Create user + email identity with hashed password stored in extra
    user, is_new = get_or_create_user_by_identity(db, "email", body.email)
    if not is_new:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Store hashed password in the identity's extra field
    identity = db.query(UserIdentity).filter(
        UserIdentity.user_id == user.id,
        UserIdentity.type == "email",
    ).first()
    identity.extra = {"password_hash": hash_password(body.password)}
    db.commit()

    access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


# ---------------------------------------------------------------------------
# Email Login
# ---------------------------------------------------------------------------


@router.post("/email/login", response_model=TokenResponse)
def email_login(body: EmailLoginRequest, db: Session = Depends(get_db)):
    """Authenticate with email and password."""
    from app.models import UserIdentity

    identity = db.query(UserIdentity).filter(
        UserIdentity.type == "email",
        UserIdentity.identifier == body.email,
    ).first()
    if not identity:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    password_hash = identity.extra.get("password_hash")
    if not password_hash or not verify_password(body.password, password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    user = db.query(User).filter(User.id == identity.user_id).first()
    if not user or user.status != 0:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or disabled",
        )

    access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


# ---------------------------------------------------------------------------
# Email Verification (placeholder - requires email sending service)
# ---------------------------------------------------------------------------


@router.post("/email/send-otp")
def email_send_otp(body: EmailSendOtpRequest, db: Session = Depends(get_db)):
    """Request an OTP code for email verification.

    TODO: Integrate with an email sending service (e.g. SendGrid, SES).
    For now, this is a placeholder that generates and stores the OTP hash.
    """
    from app.models import VaultEmailOtp
    from datetime import timedelta
    import hashlib
    import secrets

    # Generate a 6-digit OTP
    otp_code = f"{secrets.randbelow(1000000):06d}"
    code_hash = hashlib.sha256(otp_code.encode()).hexdigest()

    otp_record = VaultEmailOtp(
        user_id=None,  # Will be set when user is known
        email=body.email,
        code_hash=code_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    db.add(otp_record)
    db.commit()

    # TODO: Send email with OTP code
    # For development, return the code in response (remove in production!)
    return {"detail": "OTP sent", "_dev_otp_code": otp_code}


@router.post("/email/verify")
def email_verify(body: EmailVerifyRequest, db: Session = Depends(get_db)):
    """Verify an email with OTP code."""
    import hashlib
    from app.models import VaultEmailOtp

    code_hash = hashlib.sha256(body.code.encode()).hexdigest()

    otp_record = db.query(VaultEmailOtp).filter(
        VaultEmailOtp.email == body.email,
        VaultEmailOtp.code_hash == code_hash,
        VaultEmailOtp.consumed_at.is_(None),
        VaultEmailOtp.expires_at > datetime.now(timezone.utc),
    ).first()

    if not otp_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP code",
        )

    # Mark OTP as consumed
    otp_record.consumed_at = datetime.now(timezone.utc)
    db.commit()

    # Mark the email identity as verified
    from app.models import UserIdentity

    identity = db.query(UserIdentity).filter(
        UserIdentity.type == "email",
        UserIdentity.identifier == body.email,
    ).first()
    if identity:
        identity.verified_at = datetime.now(timezone.utc)
        db.commit()

    return {"detail": "Email verified successfully"}


# ---------------------------------------------------------------------------
# WeChat Mini Program Login
# ---------------------------------------------------------------------------


@router.post("/wechat/login", response_model=WechatLoginResponse)
def wechat_login(body: WechatLoginRequest, db: Session = Depends(get_db)):
    """Login via WeChat Mini Program.

    TODO: Exchange the wx.login code for openid/unionid via WeChat API.
    For now, this is a placeholder that accepts the code directly as openid.
    """
    # TODO: Call WeChat API to exchange code for openid/unionid
    #   GET https://api.weixin.qq.com/sns/jscode2session
    #   ?appid={APPID}&secret={SECRET}&js_code={code}&grant_type=authorization_code
    openid = body.code  # Placeholder: using code as openid directly
    unionid = None  # TODO: extract from WeChat response

    # Use unionid as primary identifier if available, otherwise openid
    identifier = unionid if unionid else openid
    identity_type = "wechat"

    user, is_new = get_or_create_user_by_identity(
        db, identity_type, identifier, provider="wechat_miniprogram"
    )

    # If unionid is available and different from openid, also bind openid
    if unionid and openid and unionid != openid:
        try:
            bind_identity_to_user(
                db, user, "wechat", openid,
                provider="wechat_miniprogram_openid",
            )
        except ValueError:
            pass  # Already bound, ignore

    # Store nickname/avatar if provided and user is new
    if is_new and (body.nickname or body.avatar_url):
        identity = db.query(UserIdentity).filter(
            UserIdentity.user_id == user.id,
            UserIdentity.type == "wechat",
            UserIdentity.identifier == identifier,
        ).first()
        if identity:
            extra = identity.extra or {}
            if body.nickname:
                extra["nickname"] = body.nickname
            if body.avatar_url:
                extra["avatar_url"] = body.avatar_url
            identity.extra = extra
            db.commit()

    access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))
    return WechatLoginResponse(
        user_id=str(user.id),
        access_token=access_token,
        refresh_token=refresh_token,
        is_new=is_new,
    )


# ---------------------------------------------------------------------------
# Token Refresh
# ---------------------------------------------------------------------------


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(body: RefreshRequest, db: Session = Depends(get_db)):
    """Exchange a valid refresh token for a new access token pair."""
    from jose import JWTError

    try:
        payload = decode_token(body.refresh_token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user or user.status != 0:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or disabled",
        )

    access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


# ---------------------------------------------------------------------------
# Current User Profile
# ---------------------------------------------------------------------------


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    """Get the current authenticated user's profile."""
    identities = []
    for ident in current_user.identities:
        info = {"type": ident.type, "verified": ident.verified_at is not None}
        # Mask sensitive identifiers
        if ident.type == "email":
            info["identifier"] = ident.identifier[:3] + "***" + ident.identifier.split("@")[-1]
        elif ident.type == "phone" and not ident.extra.get("is_guest"):
            info["identifier"] = ident.identifier[:3] + "****" + ident.identifier[-4:]
        elif ident.type == "wechat":
            info["provider"] = ident.provider
            if ident.extra.get("nickname"):
                info["nickname"] = ident.extra["nickname"]
        identities.append(info)

    return {
        "user_id": str(current_user.id),
        "identities": identities,
        "created_at": current_user.created_at.isoformat(),
    }
