"""Authentication service layer.

Contains business logic for user creation, identity binding,
and credential verification.
"""

import secrets
from datetime import datetime, timezone

from jose import JWTError
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.models import User, UserIdentity

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


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
