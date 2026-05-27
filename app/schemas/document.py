"""Pydantic schemas for document library (folders and files)."""

from datetime import datetime

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Folder
# ---------------------------------------------------------------------------


class FolderCreateRequest(BaseModel):
    """Request body for creating a folder."""

    zone: str = Field(description="'shared' or 'vault'")
    name: str = Field(min_length=1, max_length=100)
    parent_id: str | None = None


class FolderUpdateRequest(BaseModel):
    """Request body for updating a folder."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    parent_id: str | None = None


class FolderResponse(BaseModel):
    """Folder data returned by API."""

    folder_id: str
    family_id: str
    zone: str
    name: str
    parent_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FolderListResponse(BaseModel):
    """List of folders."""

    folders: list[FolderResponse]


# ---------------------------------------------------------------------------
# File
# ---------------------------------------------------------------------------


class FileUploadRequest(BaseModel):
    """Request body for registering a file upload.

    The actual file upload happens via signed URL to object storage.
    This endpoint registers the metadata after successful upload.
    """

    filename: str = Field(min_length=1, max_length=255)
    mime_type: str
    size_bytes: int = Field(ge=0, le=20_971_520)  # 20MB max
    storage_key: str
    checksum: str | None = None
    folder_id: str | None = None


class FileResponse(BaseModel):
    """File metadata returned by API."""

    file_id: str
    family_id: str
    zone: str
    folder_id: str | None
    filename: str
    mime_type: str
    size_bytes: int
    storage_key: str
    checksum: str | None
    uploader_user_id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FileListResponse(BaseModel):
    """List of files."""

    files: list[FileResponse]
    total: int


# ---------------------------------------------------------------------------
# Vault
# ---------------------------------------------------------------------------


class VaultOtpRequest(BaseModel):
    """Request body for requesting vault access OTP."""

    email: str


class VaultOtpVerifyRequest(BaseModel):
    """Request body for verifying vault OTP."""

    email: str
    code: str = Field(min_length=6, max_length=6)


class VaultSessionResponse(BaseModel):
    """Vault session data returned by API."""

    session_id: str
    family_id: str
    expires_at: datetime

    model_config = {"from_attributes": True}
