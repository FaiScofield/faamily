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

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.permissions import require_admin, require_any_role
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
from app.services.document_service import (
    create_file,
    create_folder,
    create_vault_otp,
    create_vault_session,
    delete_folder,
    get_file,
    get_folder,
    get_valid_vault_session,
    list_files,
    list_folders,
    soft_delete_file,
    update_folder,
    verify_vault_otp,
)

router = APIRouter(prefix="/families/{family_id}/documents", tags=["documents"])


# ---------------------------------------------------------------------------
# Folders
# ---------------------------------------------------------------------------


@router.post("/folders", response_model=FolderResponse, status_code=status.HTTP_201_CREATED)
def create_new_folder(
    family_id: str,
    body: FolderCreateRequest,
    membership: Membership = Depends(require_any_role),
    db: Session = Depends(get_db),
):
    """Create a new folder in the document library."""
    # Validate zone
    if body.zone not in ("shared", "vault"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zone must be 'shared' or 'vault'",
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
        )

    return folder


@router.get("/folders", response_model=FolderListResponse)
def list_document_folders(
    family_id: str,
    membership: Membership = Depends(require_any_role),
    db: Session = Depends(get_db),
    zone: str | None = Query(default=None),
    parent_id: str | None = Query(default=None),
):
    """List folders in the document library."""
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
    db: Session = Depends(get_db),
):
    """Update a folder (owner or admin only)."""
    folder = get_folder(db, folder_id, family_id)
    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Folder not found",
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
    db: Session = Depends(get_db),
):
    """Delete a folder and all its contents (owner or admin only)."""
    folder = get_folder(db, folder_id, family_id)
    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Folder not found",
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
    """
    # Validate file size (20MB max)
    if body.size_bytes > 20_971_520:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size exceeds 20MB limit",
        )

    try:
        file = create_file(
            db=db,
            family_id=family_id,
            zone="shared",  # Default to shared zone
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
        )

    return file


@router.get("/files", response_model=FileListResponse)
def list_document_files(
    family_id: str,
    membership: Membership = Depends(require_any_role),
    db: Session = Depends(get_db),
    zone: str | None = Query(default=None),
    folder_id: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
):
    """List files in the document library."""
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
    db: Session = Depends(get_db),
):
    """Soft-delete a file (owner or admin only)."""
    file = get_file(db, file_id, family_id)
    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    soft_delete_file(db, file)
    return None


# ---------------------------------------------------------------------------
# Vault Access
# ---------------------------------------------------------------------------


@router.post("/vault/otp")
def request_vault_otp(
    family_id: str,
    body: VaultOtpRequest,
    membership: Membership = Depends(require_any_role),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Request an OTP for vault access.

    The OTP will be sent to the provided email address.
    TODO: Integrate with email sending service.
    """
    otp_code = create_vault_otp(
        db=db,
        user_id=str(current_user.id),
        email=body.email,
    )

    # TODO: Send email with OTP code
    # For development, return the code in response (remove in production!)
    return {
        "detail": "OTP sent to email",
        "_dev_otp_code": otp_code,  # Remove in production!
    }


@router.post("/vault/verify", response_model=VaultSessionResponse)
def verify_vault_otp_endpoint(
    family_id: str,
    body: VaultOtpVerifyRequest,
    membership: Membership = Depends(require_any_role),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Verify OTP and create a vault access session."""
    is_valid = verify_vault_otp(
        db=db,
        user_id=str(current_user.id),
        email=body.email,
        otp_code=body.code,
    )

    if not is_valid:
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
