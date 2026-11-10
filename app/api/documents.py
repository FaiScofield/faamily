"""Document library API routes (folders, files, vault).

Endpoints:
- POST   /families/{family_id}/folders              — Create folder
- GET    /families/{family_id}/folders              — List folders
- PUT    /families/{family_id}/folders/{id}         — Update folder
- DELETE /families/{family_id}/folders/{id}         — Delete folder
- POST   /families/{family_id}/files                — Register file upload
- GET    /families/{family_id}/files                — List files
- DELETE /families/{family_id}/files/{id}           — Delete file
- POST   /families/{family_id}/vault/otp            — Request vault OTP
- POST   /families/{family_id}/vault/verify         — Verify vault OTP
- GET    /families/{family_id}/vault/status         — Check vault session status
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.permissions import (
    assert_vault_session,
    require_admin,
    require_any_role,
)
from app.db import get_db
from app.models import Membership, User
from app.schemas.document import (
    FileListResponse,
    FileResponse,
    FileUploadRequest,
    FolderCreateRequest,
    FolderListResponse,
    FolderResponse,
    FolderUpdateRequest,
    VaultOtpRequest,
    VaultOtpVerifyRequest,
    VaultSessionResponse,
)
from app.services.audit_service import write_audit_log
from app.services.auth_service import send_otp_email
from app.services.document_service import (
    create_file,
    create_folder,
    create_vault_otp,
    create_vault_session,
    delete_folder,
    get_file,
    get_folder,
    get_valid_vault_session,
    get_verified_email,
    list_files,
    list_folders,
    soft_delete_file,
    update_folder,
    verify_vault_otp,
)

router = APIRouter(prefix="/families/{family_id}/documents", tags=["documents"])

# Rate limiter for vault endpoints (OTP request/verify)
limiter = Limiter(key_func=get_remote_address)


# ---------------------------------------------------------------------------
# Folders
# ---------------------------------------------------------------------------


@router.post("/folders", response_model=FolderResponse, status_code=status.HTTP_201_CREATED)
def create_new_folder(
    family_id: str,
    body: FolderCreateRequest,
    membership: Membership = Depends(require_any_role),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new folder in the document library.

    Creating a folder inside the vault zone requires a valid vault session
    (obtained by exchanging an email OTP).
    """
    # Validate zone
    if body.zone not in ("shared", "vault"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zone must be 'shared' or 'vault'",
        )

    # Vault zones are protected by a second factor
    if body.zone == "vault":
        assert_vault_session(
            db=db, user_id=str(current_user.id), family_id=family_id
        )

    try:
        folder = create_folder(
            db=db,
            family_id=family_id,
            zone=body.zone,
            name=body.name,
            parent_id=body.parent_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        ) from e

    return folder


@router.get("/folders", response_model=FolderListResponse)
def list_document_folders(
    family_id: str,
    membership: Membership = Depends(require_any_role),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    zone: str | None = Query(default=None),
    parent_id: str | None = Query(default=None),
):
    """List folders in the document library.

    Vault folders require a valid vault session when `zone=vault` is
    requested explicitly. Without an explicit `zone`, the vault zone is
    excluded so it can never be reached by omission.
    """
    if zone == "vault":
        assert_vault_session(
            db=db, user_id=str(current_user.id), family_id=family_id
        )
    elif zone is None:
        zone = "shared"

    folders = list_folders(
        db=db,
        family_id=family_id,
        zone=zone,
        parent_id=parent_id,
    )
    return FolderListResponse(folders=folders)


@router.put("/folders/{folder_id}", response_model=FolderResponse)
def update_folder_endpoint(
    family_id: str,
    folder_id: str,
    body: FolderUpdateRequest,
    membership: Membership = Depends(require_admin),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a folder (owner or admin only).

    Vault folders additionally require a valid vault session.
    """
    folder = get_folder(db, folder_id, family_id)
    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Folder not found",
        )

    if folder.zone == "vault":
        assert_vault_session(
            db=db, user_id=str(current_user.id), family_id=family_id
        )

    folder = update_folder(
        db=db,
        folder=folder,
        name=body.name,
        parent_id=body.parent_id,
    )
    return folder


@router.delete("/folders/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_folder_endpoint(
    family_id: str,
    folder_id: str,
    membership: Membership = Depends(require_admin),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a folder and all its contents (owner or admin only).

    Vault folders additionally require a valid vault session.
    """
    folder = get_folder(db, folder_id, family_id)
    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Folder not found",
        )

    if folder.zone == "vault":
        assert_vault_session(
            db=db, user_id=str(current_user.id), family_id=family_id
        )

    delete_folder(db, folder)
    return None


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------


@router.post("/files", response_model=FileResponse, status_code=status.HTTP_201_CREATED)
def register_file_upload(
    family_id: str,
    body: FileUploadRequest,
    membership: Membership = Depends(require_any_role),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Register a file upload in the document library.

    The actual file upload should be done via signed URL to object storage first.
    This endpoint registers the metadata after successful upload.

    A file placed inside a vault folder requires a valid vault session; the
    file inherits the zone of its parent folder.
    """
    # Validate file size (20MB max)
    if body.size_bytes > 20_971_520:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size exceeds 20MB limit",
        )

    # Resolve the target zone from the parent folder (if any)
    zone = "shared"
    if body.folder_id:
        parent_folder = get_folder(db, body.folder_id, family_id)
        if not parent_folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Folder not found",
            )
        zone = parent_folder.zone
        if zone == "vault":
            assert_vault_session(
            db=db, user_id=str(current_user.id), family_id=family_id
        )

    try:
        file = create_file(
            db=db,
            family_id=family_id,
            zone=zone,
            uploader_user_id=str(current_user.id),
            filename=body.filename,
            mime_type=body.mime_type,
            size_bytes=body.size_bytes,
            storage_key=body.storage_key,
            checksum=body.checksum,
            folder_id=body.folder_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    return file


@router.get("/files", response_model=FileListResponse)
def list_document_files(
    family_id: str,
    membership: Membership = Depends(require_any_role),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    zone: str | None = Query(default=None),
    folder_id: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
):
    """List files in the document library.

    Vault files require a valid vault session when `zone=vault` is requested
    explicitly. Without an explicit `zone`, the vault zone is excluded so it
    can never be reached by omission.
    """
    if zone == "vault":
        assert_vault_session(
            db=db, user_id=str(current_user.id), family_id=family_id
        )
    elif zone is None:
        zone = "shared"

    files, total = list_files(
        db=db,
        family_id=family_id,
        zone=zone,
        folder_id=folder_id,
        offset=offset,
        limit=limit,
    )
    return FileListResponse(files=files, total=total)


@router.delete("/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file_endpoint(
    family_id: str,
    file_id: str,
    membership: Membership = Depends(require_admin),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Soft-delete a file (owner or admin only).

    Vault files additionally require a valid vault session.
    """
    file = get_file(db, file_id, family_id)
    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    if file.zone == "vault":
        assert_vault_session(
            db=db, user_id=str(current_user.id), family_id=family_id
        )

    soft_delete_file(db, file)
    return None


# ---------------------------------------------------------------------------
# Vault Access
# ---------------------------------------------------------------------------


@router.post("/vault/otp")
@limiter.limit("3/minute")
def request_vault_otp(
    request: Request,
    family_id: str,
    body: VaultOtpRequest,
    membership: Membership = Depends(require_any_role),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Request an OTP for vault access.

    The code is delivered by email to an address the user has already bound
    and verified. It is never returned in the response body.

    Returns 400 if the email is not a verified identity of the current user,
    and 503 if SMTP is not configured.
    """
    # The OTP must go to an email the user owns and has verified.
    verified_email = get_verified_email(db, str(current_user.id), body.email)
    if not verified_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is not a verified identity of the current user",
        )

    otp_code = create_vault_otp(
        db=db,
        user_id=str(current_user.id),
        email=verified_email,
    )

    try:
        send_otp_email(
            recipient=verified_email,
            code=otp_code,
            subject="Faamily vault access code",
            body="Use this code to unlock your family vault. It expires in 10 minutes.",
        )
    except RuntimeError as exc:
        # SMTP not configured — surface it instead of leaking the code
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to send vault verification email",
        ) from exc

    write_audit_log(
        db,
        family_id,
        str(current_user.id),
        "vault.otp_requested",
        target_type="user",
        target_id=str(current_user.id),
        detail={"email": verified_email},
    )

    return {"detail": "Verification code sent to your email"}


@router.post("/vault/verify", response_model=VaultSessionResponse)
@limiter.limit("10/minute")
def verify_vault_otp_endpoint(
    request: Request,
    family_id: str,
    body: VaultOtpVerifyRequest,
    membership: Membership = Depends(require_any_role),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Verify OTP and create a vault access session.

    The error message is intentionally generic so it does not reveal whether
    an email address is bound to the account.
    """
    is_valid = verify_vault_otp(
        db=db,
        user_id=str(current_user.id),
        email=body.email.strip().lower(),
        otp_code=body.code,
    )

    if not is_valid:
        write_audit_log(
            db,
            family_id,
            str(current_user.id),
            "vault.otp_failed",
            target_type="user",
            target_id=str(current_user.id),
            detail={"email": body.email.strip().lower()},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP code",
        )

    # Create vault session
    session = create_vault_session(
        db=db,
        user_id=str(current_user.id),
        family_id=family_id,
    )

    write_audit_log(
        db,
        family_id,
        str(current_user.id),
        "vault.session_created",
        target_type="vault_session",
        target_id=str(session.id),
        detail={"expires_at": session.expires_at.isoformat()},
    )

    return session


@router.get("/vault/status")
def check_vault_session_status(
    family_id: str,
    membership: Membership = Depends(require_any_role),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Check if the user has a valid vault access session."""
    session = get_valid_vault_session(
        db=db,
        user_id=str(current_user.id),
        family_id=family_id,
    )

    if session:
        return {
            "has_valid_session": True,
            "expires_at": session.expires_at.isoformat(),
        }
    else:
        return {
            "has_valid_session": False,
            "expires_at": None,
        }
