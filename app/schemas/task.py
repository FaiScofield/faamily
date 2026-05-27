"""Pydantic schemas for task-related request/response models."""

from datetime import datetime

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------


class TaskCreateRequest(BaseModel):
    """Request body for creating a new task."""

    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    assignee_user_id: str | None = None
    reviewer_user_id: str | None = None
    due_at: datetime | None = None
    priority: int = Field(default=0, ge=0, le=3, description="0=none, 1=low, 2=medium, 3=high")
    repeat_rule: dict | None = None


class TaskUpdateRequest(BaseModel):
    """Request body for updating a task."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    assignee_user_id: str | None = None
    reviewer_user_id: str | None = None
    due_at: datetime | None = None
    priority: int | None = Field(default=None, ge=0, le=3)
    repeat_rule: dict | None = None


class TaskStatusUpdateRequest(BaseModel):
    """Request body for updating task status (state machine transition)."""

    status: str = Field(description="Target status: pending, in_progress, submitted")


class TaskResponse(BaseModel):
    """Task data returned by API."""

    task_id: str
    family_id: str
    title: str
    description: str | None
    created_by_user_id: str
    assignee_user_id: str | None
    reviewer_user_id: str | None
    due_at: datetime | None
    priority: int
    status: str
    repeat_rule: dict | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TaskListResponse(BaseModel):
    """Paginated list of tasks."""

    tasks: list[TaskResponse]
    total: int


# ---------------------------------------------------------------------------
# Task Submission
# ---------------------------------------------------------------------------


class SubmissionCreateRequest(BaseModel):
    """Request body for submitting a task."""

    note: str | None = None
    attachment_ids: list[str] = Field(default_factory=list, description="File IDs attached as proof")


class SubmissionReviewRequest(BaseModel):
    """Request body for reviewing a task submission."""

    status: str = Field(description="'approved' or 'rejected'")
    review_note: str | None = None


class SubmissionResponse(BaseModel):
    """Submission data returned by API."""

    submission_id: str
    task_id: str
    submitted_by_user_id: str
    note: str | None
    status: str
    review_note: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SubmissionListResponse(BaseModel):
    """List of submissions for a task."""

    submissions: list[SubmissionResponse]
