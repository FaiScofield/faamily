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

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.db import get_db
from app.models import User, UserIdentity
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
from app.services import auth_service
from app.services.auth_service import (
    create_anonymous_user,
    get_or_create_user_by_identity,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# Rate limiter for auth endpoints
limiter = Limiter(key_func=get_remote_address)


# ---------------------------------------------------------------------------
# Guest Login
# ---------------------------------------------------------------------------


@router.post("/guest", response_model=GuestLoginResponse)
@limiter.limit("5/minute")
def guest_login(request: Request, db: Session = Depends(get_db)):
    """Create an anonymous guest user and return tokens."""
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
@limiter.limit("3/minute")
def email_register(request: Request, body: EmailRegisterRequest, db: Session = Depends(get_db)):
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
@limiter.limit("10/minute")
def email_login(request: Request, body: EmailLoginRequest, db: Session = Depends(get_db)):
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
# Email Verification
# ---------------------------------------------------------------------------


@router.post("/email/send-otp")
@limiter.limit("3/minute")
def email_send_otp(request: Request, body: EmailSendOtpRequest, db: Session = Depends(get_db)):
    """Create and send an email verification OTP."""
    otp_code = auth_service.generate_otp_code()

    try:
        auth_service.create_email_verification_otp(db, body.email, otp_code)
        auth_service.send_email_otp(body.email, otp_code)
        db.commit()
    except RuntimeError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to send verification email",
        )

    return {"detail": "Verification code sent"}


@router.post("/email/verify")
def email_verify(body: EmailVerifyRequest, db: Session = Depends(get_db)):
    """Verify an email using a previously sent OTP code."""
    try:
        auth_service.verify_email_otp(db, body.email, body.code)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    return {"detail": "Email verified successfully"}


# ---------------------------------------------------------------------------
# WeChat Mini Program Login
# ---------------------------------------------------------------------------


@router.post("/wechat/login", response_model=WechatLoginResponse)
@limiter.limit("10/minute")
def wechat_login(request: Request, body: WechatLoginRequest, db: Session = Depends(get_db)):
    """Login via WeChat Mini Program using the jscode2session API."""
    try:
        session_payload = auth_service.exchange_wechat_code_for_session(body.code)
    except auth_service.WechatConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    except auth_service.WechatAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"errcode": exc.errcode, "errmsg": exc.errmsg},
        )
    except auth_service.WechatUpstreamError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )

    openid = session_payload["openid"]
    unionid = session_payload.get("unionid")
    identifier = unionid or openid

    user, is_new = auth_service.get_or_create_user_by_wechat_session(
        db,
        openid=openid,
        unionid=unionid,
    )

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
