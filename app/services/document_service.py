"""Document library business logic service layer.

Handles folders, files, and vault access with OTP verification.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import File, Folder, Quota, VaultEmailOtp, VaultSession


# ---------------------------------------------------------------------------
# Folder
# ---------------------------------------------------------------------------


def create_folder(
    db: Session,
    family_id: str,
    zone: str,
    name: str,
    parent_id: str | None = None,
) -> Folder:
    """Create a new folder in the document library.

    Args:
        db: Database session.
        family_id: UUID of the family.
        zone: 'shared' or 'vault'.
        name: Folder name.
        parent_id: Optional parent folder ID.

    Returns:
        The newly created Folder object.

    Raises:
        ValueError: If folder with same name exists in same parent.
    """
    # Check for duplicate name in same parent
    existing = db.query(Folder).filter(
        Folder.family_id == family_id,
        Folder.zone == zone,
        Folder.name == name,
        Folder.parent_id == parent_id,
    ).first()

    if existing:
        raise ValueError(f"Folder '{name}' already exists in this location")

    folder = Folder(
        family_id=family_id,
        zone=zone,
        name=name,
        parent_id=parent_id,
    )
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return folder


def get_folder(db: Session, folder_id: str, family_id: str) -> Folder | None:
    """Get a folder by ID and family."""
    return db.query(Folder).filter(
        Folder.id == folder_id,
        Folder.family_id == family_id,
    ).first()


def list_folders(
    db: Session,
    family_id: str,
    zone: str | None = None,
    parent_id: str | None = None,
) -> list[Folder]:
    """List folders in a family.

    Args:
        db: Database session.
        family_id: UUID of the family.
        zone: Optional filter by zone ('shared' or 'vault').
        parent_id: Optional filter by parent folder.

    Returns:
        List of Folder objects.
    """
    query = db.query(Folder).filter(Folder.family_id == family_id)

    if zone:
        query = query.filter(Folder.zone == zone)
    if parent_id is not None:
        query = query.filter(Folder.parent_id == parent_id)
    else:
        query = query.filter(Folder.parent_id.is_(None))

    return query.order_by(Folder.name).all()


def update_folder(
    db: Session,
    folder: Folder,
    name: str | None = None,
    parent_id: str | None = None,
) -> Folder:
    """Update folder fields."""
    if name is not None:
        folder.name = name
    if parent_id is not None:
        folder.parent_id = parent_id

    db.commit()
    db.refresh(folder)
    return folder


def delete_folder(db: Session, folder: Folder) -> None:
    """Delete a folder and all its contents."""
    db.delete(folder)
    db.commit()


# ---------------------------------------------------------------------------
# File
# ---------------------------------------------------------------------------


def create_file(
    db: Session,
    family_id: str,
    zone: str,
    uploader_user_id: str,
    filename: str,
    mime_type: str,
    size_bytes: int,
    storage_key: str,
    checksum: str | None = None,
    folder_id: str | None = None,
) -> File:
    """Register a file in the document library.

    Args:
        db: Database session.
        family_id: UUID of the family.
        zone: 'shared', 'vault', or 'attachment'.
        uploader_user_id: UUID of the uploading user.
        filename: Original filename.
        mime_type: MIME type.
        size_bytes: File size in bytes.
        storage_key: Object storage key.
        checksum: Optional file checksum.
        folder_id: Optional parent folder ID.

    Returns:
        The newly created File object.

    Raises:
        ValueError: If storage quota would be exceeded.
    """
    # Check quota
    quota = db.query(Quota).filter(Quota.family_id == family_id).first()
    if quota:
        if quota.used_bytes + size_bytes > quota.total_bytes:
            raise ValueError("Storage quota exceeded")
        quota.used_bytes += size_bytes

    file = File(
        family_id=family_id,
        zone=zone,
        folder_id=folder_id,
        owner_type="document",
        owner_id=None,
        uploader_user_id=uploader_user_id,
        filename=filename,
        mime_type=mime_type,
        size_bytes=size_bytes,
        storage_key=storage_key,
        checksum=checksum,
    )
    db.add(file)
    db.commit()
    db.refresh(file)
    return file


def get_file(db: Session, file_id: str, family_id: str) -> File | None:
    """Get a file by ID and family."""
    return db.query(File).filter(
        File.id == file_id,
        File.family_id == family_id,
        File.deleted_at.is_(None),
    ).first()


def list_files(
    db: Session,
    family_id: str,
    zone: str | None = None,
    folder_id: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[File], int]:
    """List files in a family."""
    query = db.query(File).filter(
        File.family_id == family_id,
        File.deleted_at.is_(None),
    )

    if zone:
        query = query.filter(File.zone == zone)
    if folder_id is not None:
        query = query.filter(File.folder_id == folder_id)

    total = query.count()
    files = query.order_by(File.created_at.desc()).offset(offset).limit(limit).all()
    return files, total


def soft_delete_file(db: Session, file: File) -> None:
    """Soft-delete a file and update quota."""
    file.deleted_at = datetime.now(timezone.utc)

    # Update quota
    quota = db.query(Quota).filter(Quota.family_id == file.family_id).first()
    if quota:
        quota.used_bytes = max(0, quota.used_bytes - file.size_bytes)

    db.commit()


# ---------------------------------------------------------------------------
# Vault Access (OTP)
# ---------------------------------------------------------------------------


def generate_otp() -> str:
    """Generate a 6-digit OTP code."""
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(otp: str) -> str:
    """Hash an OTP for secure storage."""
    return hashlib.sha256(otp.encode()).hexdigest()


def create_vault_otp(
    db: Session,
    user_id: str,
    email: str,
    expires_in_minutes: int = 10,
) -> str:
    """Create a new vault access OTP.

    Args:
        db: Database session.
        user_id: UUID of the user.
        email: Email address to send OTP to.
        expires_in_minutes: OTP expiration time.

    Returns:
        The plain OTP code (to be sent to user).
    """
    otp_code = generate_otp()
    otp_hash = hash_otp(otp_code)

    otp_record = VaultEmailOtp(
        user_id=user_id,
        email=email,
        code_hash=otp_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes),
    )
    db.add(otp_record)
    db.commit()

    return otp_code


def verify_vault_otp(
    db: Session,
    user_id: str,
    email: str,
    otp_code: str,
) -> bool:
    """Verify a vault access OTP.

    Args:
        db: Database session.
        user_id: UUID of the user.
        email: Email address.
        otp_code: The OTP code entered by user.

    Returns:
        True if OTP is valid and not expired.
    """
    otp_hash = hash_otp(otp_code)

    otp_record = db.query(VaultEmailOtp).filter(
        VaultEmailOtp.user_id == user_id,
        VaultEmailOtp.email == email,
        VaultEmailOtp.code_hash == otp_hash,
        VaultEmailOtp.consumed_at.is_(None),
        VaultEmailOtp.expires_at > datetime.now(timezone.utc),
    ).first()

    if not otp_record:
        return False

    # Mark as consumed
    otp_record.consumed_at = datetime.now(timezone.utc)
    db.commit()

    return True


# ---------------------------------------------------------------------------
# Vault Session
# ---------------------------------------------------------------------------


def create_vault_session(
    db: Session,
    user_id: str,
    family_id: str,
    expires_in_minutes: int = 30,
) -> VaultSession:
    """Create a vault access session after successful OTP verification.

    Args:
        db: Database session.
        user_id: UUID of the user.
        family_id: UUID of the family.
        expires_in_minutes: Session expiration time.

    Returns:
        The newly created VaultSession object.
    """
    session = VaultSession(
        user_id=user_id,
        family_id=family_id,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_valid_vault_session(
    db: Session,
    user_id: str,
    family_id: str,
) -> VaultSession | None:
    """Get a valid (non-expired, non-revoked) vault session.

    Args:
        db: Database session.
        user_id: UUID of the user.
        family_id: UUID of the family.

    Returns:
        Valid VaultSession or None.
    """
    return db.query(VaultSession).filter(
        VaultSession.user_id == user_id,
        VaultSession.family_id == family_id,
        VaultSession.expires_at > datetime.now(timezone.utc),
        VaultSession.revoked_at.is_(None),
    ).first()


def revoke_vault_session(db: Session, session: VaultSession) -> None:
    """Revoke a vault session."""
    session.revoked_at = datetime.now(timezone.utc)
    db.commit()
