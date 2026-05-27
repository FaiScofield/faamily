"""Task business logic service layer.

Handles task CRUD, state machine transitions, and submission review.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Task, TaskSubmission, User


# ---------------------------------------------------------------------------
# Valid status transitions
# ---------------------------------------------------------------------------

VALID_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"in_progress", "done"},
    "in_progress": {"submitted", "pending"},
    "submitted": {"done", "rejected"},
    "rejected": {"in_progress"},
    "done": set(),  # Terminal state
}


def is_valid_transition(current_status: str, target_status: str) -> bool:
    """Check if a status transition is valid.

    Args:
        current_status: Current task status.
        target_status: Desired target status.

    Returns:
        True if the transition is allowed.
    """
    allowed = VALID_TRANSITIONS.get(current_status, set())
    return target_status in allowed


# ---------------------------------------------------------------------------
# Task CRUD
# ---------------------------------------------------------------------------


def create_task(
    db: Session,
    family_id: str,
    created_by: User,
    title: str,
    description: str | None = None,
    assignee_user_id: str | None = None,
    reviewer_user_id: str | None = None,
    due_at: datetime | None = None,
    priority: int = 0,
    repeat_rule: dict | None = None,
) -> Task:
    """Create a new task in a family.

    Args:
        db: Database session.
        family_id: UUID of the family.
        created_by: User creating the task.
        title: Task title.
        description: Optional description.
        assignee_user_id: Optional user to assign the task to.
        reviewer_user_id: Optional user to review the task.
        due_at: Optional due date.
        priority: Priority level (0-3).
        repeat_rule: Optional repeat rule JSON.

    Returns:
        The newly created Task object.
    """
    task = Task(
        family_id=family_id,
        title=title,
        description=description,
        created_by_user_id=created_by.id,
        assignee_user_id=assignee_user_id,
        reviewer_user_id=reviewer_user_id,
        due_at=due_at,
        priority=priority,
        repeat_rule=repeat_rule,
        status="pending",
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def get_task(db: Session, task_id: str, family_id: str) -> Task | None:
    """Get a single task by ID and family (ensures data isolation)."""
    return db.query(Task).filter(
        Task.id == task_id,
        Task.family_id == family_id,
        Task.deleted_at.is_(None),
    ).first()


def list_tasks(
    db: Session,
    family_id: str,
    assignee_user_id: str | None = None,
    status: str | None = None,
    due_before: datetime | None = None,
    due_after: datetime | None = None,
    priority: int | None = None,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[Task], int]:
    """List tasks with filtering and pagination.

    Args:
        db: Database session.
        family_id: UUID of the family.
        assignee_user_id: Filter by assignee.
        status: Filter by status.
        due_before: Filter tasks due before this datetime.
        due_after: Filter tasks due after this datetime.
        priority: Filter by priority level.
        offset: Pagination offset.
        limit: Pagination limit.

    Returns:
        Tuple of (tasks list, total count).
    """
    query = db.query(Task).filter(
        Task.family_id == family_id,
        Task.deleted_at.is_(None),
    )

    if assignee_user_id:
        query = query.filter(Task.assignee_user_id == assignee_user_id)
    if status:
        query = query.filter(Task.status == status)
    if due_before:
        query = query.filter(Task.due_at <= due_before)
    if due_after:
        query = query.filter(Task.due_at >= due_after)
    if priority is not None:
        query = query.filter(Task.priority == priority)

    total = query.count()
    tasks = query.order_by(Task.created_at.desc()).offset(offset).limit(limit).all()
    return tasks, total


def update_task(
    db: Session,
    task: Task,
    title: str | None = None,
    description: str | None = None,
    assignee_user_id: str | None = None,
    reviewer_user_id: str | None = None,
    due_at: datetime | None = None,
    priority: int | None = None,
    repeat_rule: dict | None = None,
) -> Task:
    """Update task fields.

    Only non-None fields will be updated.

    Args:
        db: Database session.
        task: Task to update.
        title: New title.
        description: New description.
        assignee_user_id: New assignee.
        reviewer_user_id: New reviewer.
        due_at: New due date.
        priority: New priority.
        repeat_rule: New repeat rule.

    Returns:
        Updated Task object.
    """
    if title is not None:
        task.title = title
    if description is not None:
        task.description = description
    if assignee_user_id is not None:
        task.assignee_user_id = assignee_user_id
    if reviewer_user_id is not None:
        task.reviewer_user_id = reviewer_user_id
    if due_at is not None:
        task.due_at = due_at
    if priority is not None:
        task.priority = priority
    if repeat_rule is not None:
        task.repeat_rule = repeat_rule

    db.commit()
    db.refresh(task)
    return task


def soft_delete_task(db: Session, task: Task) -> None:
    """Soft-delete a task by setting deleted_at."""
    task.deleted_at = datetime.now(timezone.utc)
    db.commit()


# ---------------------------------------------------------------------------
# Task Status Machine
# ---------------------------------------------------------------------------


def transition_task_status(
    db: Session,
    task: Task,
    target_status: str,
) -> Task:
    """Transition a task to a new status following the state machine rules.

    Valid transitions:
    - pending → in_progress | done
    - in_progress → submitted | pending
    - submitted → done | rejected
    - rejected → in_progress
    - done → (terminal)

    Args:
        db: Database session.
        task: Task to transition.
        target_status: Desired new status.

    Returns:
        Updated Task object.

    Raises:
        ValueError: If the transition is invalid.
    """
    if not is_valid_transition(task.status, target_status):
        raise ValueError(
            f"Invalid status transition: '{task.status}' → '{target_status}'. "
            f"Allowed: {', '.join(sorted(VALID_TRANSITIONS.get(task.status, set())))}"
        )

    task.status = target_status
    db.commit()
    db.refresh(task)
    return task


# ---------------------------------------------------------------------------
# Task Submission
# ---------------------------------------------------------------------------


def create_submission(
    db: Session,
    task: Task,
    submitted_by: User,
    note: str | None = None,
) -> TaskSubmission:
    """Create a task submission (assignee submits work for review).

    Automatically transitions the task to 'submitted' status.

    Args:
        db: Database session.
        task: Task being submitted.
        submitted_by: User submitting the task.
        note: Optional note/description.

    Returns:
        The newly created TaskSubmission object.
    """
    # Transition task status
    transition_task_status(db, task, "submitted")

    submission = TaskSubmission(
        family_id=task.family_id,
        task_id=task.id,
        submitted_by_user_id=submitted_by.id,
        note=note,
        status="submitted",
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)
    return submission


def get_task_submissions(db: Session, task_id: str) -> list[TaskSubmission]:
    """Get all submissions for a task, ordered by creation time."""
    return db.query(TaskSubmission).filter(
        TaskSubmission.task_id == task_id,
    ).order_by(TaskSubmission.created_at.desc()).all()


def review_submission(
    db: Session,
    submission: TaskSubmission,
    review_status: str,
    review_note: str | None = None,
) -> TaskSubmission:
    """Review a task submission (approve or reject).

    Automatically transitions the parent task status:
    - approved → task becomes 'done'
    - rejected → task becomes 'rejected'

    Args:
        db: Database session.
        submission: Submission to review.
        review_status: 'approved' or 'rejected'.
        review_note: Optional review note.

    Returns:
        Updated TaskSubmission object.

    Raises:
        ValueError: If review_status is invalid.
    """
    if review_status not in ("approved", "rejected"):
        raise ValueError("Review status must be 'approved' or 'rejected'")

    submission.status = review_status
    submission.review_note = review_note

    # Transition parent task status
    task = db.query(Task).filter(Task.id == submission.task_id).first()
    if task:
        target = "done" if review_status == "approved" else "rejected"
        transition_task_status(db, task, target)

    db.commit()
    db.refresh(submission)
    return submission
