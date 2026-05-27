"""Task API routes.

Endpoints:
- POST   /families/{family_id}/tasks              — Create a task
- GET    /families/{family_id}/tasks              — List tasks (with filters)
- GET    /families/{family_id}/tasks/{task_id}    — Get task details
- PUT    /families/{family_id}/tasks/{task_id}    — Update task
- DELETE /families/{family_id}/tasks/{task_id}    — Soft-delete task
- PUT    /families/{family_id}/tasks/{task_id}/status — Transition status
- POST   /families/{family_id}/tasks/{task_id}/submit  — Submit task for review
- GET    /families/{family_id}/tasks/{task_id}/submissions — List submissions
- PUT    /families/{family_id}/tasks/{task_id}/submissions/{sub_id}/review — Review
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.permissions import require_admin, require_any_role
from app.db import get_db
from app.models import Membership, Task, TaskSubmission, User
from app.schemas.task import (
    SubmissionCreateRequest,
    SubmissionListResponse,
    SubmissionResponse,
    SubmissionReviewRequest,
    TaskCreateRequest,
    TaskListResponse,
    TaskResponse,
    TaskStatusUpdateRequest,
    TaskUpdateRequest,
)
from app.services.task_service import (
    create_submission,
    create_task,
    get_task,
    get_task_submissions,
    is_valid_transition,
    list_tasks,
    review_submission,
    soft_delete_task,
    transition_task_status,
    update_task,
)

router = APIRouter(prefix="/families/{family_id}/tasks", tags=["tasks"])


# ---------------------------------------------------------------------------
# Task CRUD
# ---------------------------------------------------------------------------


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_new_task(
    family_id: str,
    body: TaskCreateRequest,
    membership: Membership = Depends(require_admin),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new task (owner or admin only)."""
    task = create_task(
        db=db,
        family_id=family_id,
        created_by=current_user,
        title=body.title,
        description=body.description,
        assignee_user_id=body.assignee_user_id,
        reviewer_user_id=body.reviewer_user_id,
        due_at=body.due_at,
        priority=body.priority,
        repeat_rule=body.repeat_rule,
    )
    return task


@router.get("", response_model=TaskListResponse)
def list_family_tasks(
    family_id: str,
    membership: Membership = Depends(require_any_role),
    db: Session = Depends(get_db),
    assignee_user_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    due_before: datetime | None = Query(default=None),
    due_after: datetime | None = Query(default=None),
    priority: int | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
):
    """List tasks in a family with optional filters."""
    tasks, total = list_tasks(
        db=db,
        family_id=family_id,
        assignee_user_id=assignee_user_id,
        status=status,
        due_before=due_before,
        due_after=due_after,
        priority=priority,
        offset=offset,
        limit=limit,
    )
    return TaskListResponse(tasks=tasks, total=total)


@router.get("/{task_id}", response_model=TaskResponse)
def get_task_details(
    family_id: str,
    task_id: str,
    membership: Membership = Depends(require_any_role),
    db: Session = Depends(get_db),
):
    """Get details of a specific task."""
    task = get_task(db, task_id, family_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    return task


@router.put("/{task_id}", response_model=TaskResponse)
def update_task_endpoint(
    family_id: str,
    task_id: str,
    body: TaskUpdateRequest,
    membership: Membership = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update task details (owner or admin only)."""
    task = get_task(db, task_id, family_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    task = update_task(
        db=db,
        task=task,
        title=body.title,
        description=body.description,
        assignee_user_id=body.assignee_user_id,
        reviewer_user_id=body.reviewer_user_id,
        due_at=body.due_at,
        priority=body.priority,
        repeat_rule=body.repeat_rule,
    )
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task_endpoint(
    family_id: str,
    task_id: str,
    membership: Membership = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Soft-delete a task (owner or admin only)."""
    task = get_task(db, task_id, family_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    soft_delete_task(db, task)
    return None


# ---------------------------------------------------------------------------
# Task Status Machine
# ---------------------------------------------------------------------------


@router.put("/{task_id}/status", response_model=TaskResponse)
def update_task_status(
    family_id: str,
    task_id: str,
    body: TaskStatusUpdateRequest,
    membership: Membership = Depends(require_any_role),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Transition task status following the state machine rules.

    Only the assignee can transition to 'in_progress' or 'submitted'.
    Owner/admin can transition any status.
    """
    task = get_task(db, task_id, family_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    # Permission check: only assignee or admin can change status
    is_assignee = str(task.assignee_user_id) == str(current_user.id)
    is_admin = membership.role in ("owner", "admin")

    if not is_assignee and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assignee or an admin can change task status",
        )

    # Assignee can only move to in_progress or submitted
    if is_assignee and not is_admin:
        if body.status not in ("in_progress", "submitted"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Assignee can only transition to 'in_progress' or 'submitted'",
            )

    try:
        task = transition_task_status(db, task, body.status)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return task


# ---------------------------------------------------------------------------
# Task Submission
# ---------------------------------------------------------------------------


@router.post("/{task_id}/submit", response_model=SubmissionResponse, status_code=status.HTTP_201_CREATED)
def submit_task(
    family_id: str,
    task_id: str,
    body: SubmissionCreateRequest,
    membership: Membership = Depends(require_any_role),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit a task for review.

    Only the assignee can submit. Automatically transitions task to 'submitted'.
    """
    task = get_task(db, task_id, family_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    # Only assignee can submit
    if str(task.assignee_user_id) != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assignee can submit this task",
        )

    if task.status not in ("in_progress", "pending"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot submit task in '{task.status}' status. Must be 'in_progress' or 'pending'.",
        )

    submission = create_submission(
        db=db,
        task=task,
        submitted_by=current_user,
        note=body.note,
    )
    return submission


@router.get("/{task_id}/submissions", response_model=SubmissionListResponse)
def list_task_submissions(
    family_id: str,
    task_id: str,
    membership: Membership = Depends(require_any_role),
    db: Session = Depends(get_db),
):
    """List all submissions for a task."""
    # Verify task exists in this family
    task = get_task(db, task_id, family_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    submissions = get_task_submissions(db, task_id)
    return SubmissionListResponse(submissions=submissions)


@router.put("/{task_id}/submissions/{submission_id}/review", response_model=SubmissionResponse)
def review_task_submission(
    family_id: str,
    task_id: str,
    submission_id: str,
    body: SubmissionReviewRequest,
    membership: Membership = Depends(require_admin),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Review a task submission (approve or reject).

    Only the reviewer or an owner/admin can review.
    Automatically transitions the task to 'done' or 'rejected'.
    """
    # Verify task exists in this family
    task = get_task(db, task_id, family_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    submission = db.query(TaskSubmission).filter(
        TaskSubmission.id == submission_id,
        TaskSubmission.task_id == task_id,
    ).first()

    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found",
        )

    # Only reviewer or admin can review
    is_reviewer = str(task.reviewer_user_id) == str(current_user.id)
    is_admin = membership.role in ("owner", "admin")

    if not is_reviewer and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the reviewer or an admin can review submissions",
        )

    try:
        submission = review_submission(
            db=db,
            submission=submission,
            review_status=body.status,
            review_note=body.review_note,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return submission
