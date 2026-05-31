"""Authentication service layer.

Contains business logic for user creation, identity binding,
and credential verification.
"""

import hashlib
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

import httpx
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import EmailVerificationOtp, User, UserIdentity

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class WechatConfigError(RuntimeError):
    """Raised when WeChat Mini Program credentials are missing."""


class WechatAPIError(RuntimeError):
    """Raised when WeChat returns a business-level error code."""

    def __init__(self, errcode: int, errmsg: str):
        """Store the WeChat errcode and errmsg for API mapping."""
        self.errcode = errcode
        self.errmsg = errmsg
        super().__init__(f"WeChat API error {errcode}: {errmsg}")


class WechatUpstreamError(RuntimeError):
    """Raised when the upstream WeChat HTTP request fails."""


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_anonymous_user(db: Session) -> User:
    """Create a new anonymous (guest) user.

    Generates a random identifier and binds it as a 'phone' type identity
    with a special 'guest:' prefix to distinguish from real phone numbers.

    Args:
        db: Database session.

    Returns:
        The newly created User object.
    """
    user = User(status=0)
    db.add(user)
    db.flush()

    # Create a guest identity with random identifier
    guest_id = f"guest:{secrets.token_hex(8)}"
    identity = UserIdentity(
        user_id=user.id,
        type="phone",
        identifier=guest_id,
        verified_at=datetime.now(timezone.utc),
        extra={"is_guest": True},
    )
    db.add(identity)
    db.commit()
    db.refresh(user)
    return user


def get_or_create_user_by_identity(
    db: Session,
    identity_type: str,
    identifier: str,
    provider: str | None = None,
) -> tuple[User, bool]:
    """Find an existing user by identity or create a new one.

    Args:
        db: Database session.
        identity_type: One of 'wechat', 'phone', 'email'.
        identifier: The unique identifier for this identity type.
        provider: Optional provider name (e.g. 'wechat_miniprogram').

    Returns:
        A tuple of (User, is_new) where is_new indicates whether
        a new user was created.
    """
    identity = db.query(UserIdentity).filter(
        UserIdentity.type == identity_type,
        UserIdentity.identifier == identifier,
    ).first()

    if identity:
        db.refresh(identity.user)
        return identity.user, False

    # Create new user + identity
    user = User(status=0)
    db.add(user)
    db.flush()

    new_identity = UserIdentity(
        user_id=user.id,
        type=identity_type,
        identifier=identifier,
        provider=provider,
    )
    db.add(new_identity)
    db.commit()
    db.refresh(user)
    return user, True


def exchange_wechat_code_for_session(code: str) -> dict:
    """Exchange a WeChat Mini Program code for a session payload."""
    if not settings.wechat_app_id or not settings.wechat_app_secret:
        raise WechatConfigError("WeChat Mini Program login is not configured")

    url = f"{settings.wechat_api_base.rstrip('/')}/sns/jscode2session"
    params = {
        "appid": settings.wechat_app_id,
        "secret": settings.wechat_app_secret,
        "js_code": code,
        "grant_type": "authorization_code",
    }

    try:
        response = httpx.get(url, params=params, timeout=10.0)
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as exc:
        raise WechatUpstreamError("Failed to exchange WeChat login code") from exc
    except ValueError as exc:
        raise WechatUpstreamError("Invalid WeChat session response") from exc

    errcode = payload.get("errcode")
    if errcode:
        raise WechatAPIError(errcode, payload.get("errmsg", "Unknown WeChat error"))
    if not payload.get("openid"):
        raise WechatUpstreamError("Invalid WeChat session response")

    return payload


def get_or_create_user_by_wechat_session(
    db: Session,
    openid: str,
    unionid: str | None = None,
) -> tuple[User, bool]:
    """Resolve the user for a WeChat session with unionid-first binding."""
    if unionid:
        union_identity = db.query(UserIdentity).filter(
            UserIdentity.type == "wechat",
            UserIdentity.identifier == unionid,
        ).first()
        if union_identity:
            db.refresh(union_identity.user)
            user = union_identity.user
            is_new = False
        else:
            open_identity = db.query(UserIdentity).filter(
                UserIdentity.type == "wechat",
                UserIdentity.identifier == openid,
            ).first()
            if open_identity:
                db.refresh(open_identity.user)
                user = open_identity.user
                is_new = False
                bind_identity_to_user(
                    db,
                    user,
                    "wechat",
                    unionid,
                    provider="wechat_miniprogram",
                )
            else:
                user, is_new = get_or_create_user_by_identity(
                    db,
                    "wechat",
                    unionid,
                    provider="wechat_miniprogram",
                )

        if openid != unionid:
            open_identity = db.query(UserIdentity).filter(
                UserIdentity.type == "wechat",
                UserIdentity.identifier == openid,
            ).first()
            if not open_identity:
                try:
                    bind_identity_to_user(
                        db,
                        user,
                        "wechat",
                        openid,
                        provider="wechat_miniprogram_openid",
                    )
                except ValueError:
                    pass

        return user, is_new

    return get_or_create_user_by_identity(
        db,
        "wechat",
        openid,
        provider="wechat_miniprogram_openid",
    )


def bind_identity_to_user(
    db: Session,
    user: User,
    identity_type: str,
    identifier: str,
    provider: str | None = None,
    verified: bool = False,
) -> UserIdentity:
    """Bind a new identity to an existing user.

    Args:
        db: Database session.
        user: The User to bind the identity to.
        identity_type: One of 'wechat', 'phone', 'email'.
        identifier: The unique identifier.
        provider: Optional provider name.
        verified: Whether this identity is pre-verified.

    Returns:
        The newly created UserIdentity.

    Raises:
        ValueError: If the identity is already bound to another user.
    """
    existing = db.query(UserIdentity).filter(
        UserIdentity.type == identity_type,
        UserIdentity.identifier == identifier,
    ).first()
    if existing and existing.user_id != user.id:
        raise ValueError(f"This {identity_type} identity is already bound to another user")
    if existing:
        db.refresh(existing)
        return existing

    identity = UserIdentity(
        user_id=user.id,
        type=identity_type,
        identifier=identifier,
        provider=provider,
        verified_at=datetime.now(timezone.utc) if verified else None,
    )
    db.add(identity)
    db.commit()
    db.refresh(identity)
    return identity


def generate_otp_code() -> str:
    """Generate a six-digit OTP code for email verification."""
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp_code(code: str) -> str:
    """Hash an OTP code before persisting it."""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def create_email_verification_otp(
    db: Session,
    email: str,
    code: str,
    ttl_minutes: int = 10,
) -> EmailVerificationOtp:
    """Create and stage an email verification OTP record."""
    otp = EmailVerificationOtp(
        email=email,
        code_hash=hash_otp_code(code),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes),
    )
    db.add(otp)
    db.flush()
    return otp


def send_email_otp(recipient: str, code: str) -> None:
    """Send an email verification OTP through the configured SMTP server."""
    if not settings.smtp_host or not settings.smtp_from_email:
        raise RuntimeError("SMTP is not configured")

    message = EmailMessage()
    message["Subject"] = "Faamily verification code"
    message["From"] = settings.smtp_from_email
    message["To"] = recipient
    message.set_content(f"Your Faamily verification code is: {code}")

    if settings.smtp_use_ssl:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port) as client:
            if settings.smtp_username:
                client.login(settings.smtp_username, settings.smtp_password or "")
            client.send_message(message)
        return

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as client:
        if settings.smtp_use_tls:
            client.starttls()
        if settings.smtp_username:
            client.login(settings.smtp_username, settings.smtp_password or "")
        client.send_message(message)


def verify_email_otp(db: Session, email: str, code: str) -> EmailVerificationOtp:
    """Consume a valid email OTP and verify the matching email identity."""
    otp = db.query(EmailVerificationOtp).filter(
        EmailVerificationOtp.email == email,
        EmailVerificationOtp.code_hash == hash_otp_code(code),
        EmailVerificationOtp.consumed_at.is_(None),
        EmailVerificationOtp.expires_at > datetime.now(timezone.utc),
    ).order_by(EmailVerificationOtp.created_at.desc()).first()

    if not otp:
        raise ValueError("Invalid or expired OTP code")

    verified_at = datetime.now(timezone.utc)
    otp.consumed_at = verified_at

    identity = db.query(UserIdentity).filter(
        UserIdentity.type == "email",
        UserIdentity.identifier == email,
    ).first()
    if identity and identity.verified_at is None:
        identity.verified_at = verified_at

    db.commit()
    db.refresh(otp)
    return otp
