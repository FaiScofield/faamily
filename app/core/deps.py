"""FastAPI dependency for extracting the current user from JWT."""

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_token
from app.db import get_db
from app.models import User

security_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Extract and validate the current user from the Authorization header.

    Also updates last_activity_at for online tracking.

    Args:
        credentials: Bearer token extracted by FastAPI.
        db: Database session.

    Returns:
        The authenticated User ORM object.

    Raises:
        HTTPException 401: If token is invalid, expired, or user not found.
    """
    token = credentials.credentials
    try:
        payload = decode_token(token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if user is None or user.status != 0:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or disabled",
        )

    # Update last activity timestamp for online tracking
    user.last_activity_at = datetime.now(timezone.utc)
    db.commit()

    return user


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False)),
    db: Session = Depends(get_db),
) -> User | None:
    """Optional auth: returns the user if a valid token is provided, else None.

    Useful for endpoints that behave differently for authenticated vs anonymous users.
    """
    if credentials is None:
        return None
    try:
        return get_current_user(credentials, db)
    except HTTPException:
        return None


def require_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Require the current user to be an admin.

    Admin users are defined by UUID in the ADMIN_USER_IDS config.

    Raises:
        HTTPException 403: If the user is not an admin.
    """
    admin_ids = [uid.strip() for uid in settings.admin_user_ids.split(",") if uid.strip()]
    if str(current_user.id) not in admin_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user
