"""Task state machine for Claude Swarm.

This module implements A2A Protocol-inspired task lifecycle management.
Tasks progress through defined states and can be tracked, delegated,
and completed with full history preservation.

Task Lifecycle States:
    pending -> assigned -> working -> review -> completed
                  |          |          |
                  v          v          v
               blocked    blocked    blocked
                  |          |          |
                  v          v          v
               failed     failed     failed
                  |          |          |
                  v          v          v
              cancelled  cancelled  cancelled

Example task:
    {
        "task_id": "uuid",
        "objective": "Implement user authentication",
        "status": "working",
        "assigned_to": "agent-1",
        "created_by": "agent-0",
        "priority": "high",
        "context_id": "feature-auth",
        "constraints": ["Use JWT", "No external deps"],
        "files": ["src/auth.py"],
        "history": [...]
    }
"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from .file_lock import FileLock, FileLockTimeout
from .logging_config import get_logger
from .project import get_project_root

__all__ = [
    "TaskStatus",
    "TaskPriority",
    "Task",
    "TaskHistoryEntry",
    "TaskManager",
    "TaskNotFoundError",
    "InvalidTransitionError",
    "get_tasks_path",
]

# Constants
TASKS_FILENAME = "TASKS.json"
TASK_LOCK_TIMEOUT_SECONDS = 5.0

# Configure logging
logger = get_logger(__name__)


class TaskNotFoundError(Exception):
    """Raised when a task is not found."""

    pass


class InvalidTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""

    pass


class TaskStatus(Enum):
    """Task lifecycle states."""

    PENDING = "pending"  # Created but not assigned
    ASSIGNED = "assigned"  # Assigned to an agent
    WORKING = "working"  # Agent is actively working
    REVIEW = "review"  # Work complete, under review
    COMPLETED = "completed"  # Successfully finished
    BLOCKED = "blocked"  # Waiting on dependency
    FAILED = "failed"  # Failed with error
    CANCELLED = "cancelled"  # Cancelled by user/agent


class TaskPriority(Enum):
    """Task priority levels."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


# Valid state transitions
VALID_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {TaskStatus.ASSIGNED, TaskStatus.CANCELLED},
    TaskStatus.ASSIGNED: {
        TaskStatus.WORKING,
        TaskStatus.BLOCKED,
        TaskStatus.CANCELLED,
        TaskStatus.PENDING,  # Unassign
    },
    TaskStatus.WORKING: {
        TaskStatus.REVIEW,
        TaskStatus.BLOCKED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
        TaskStatus.COMPLETED,  # Skip review for simple tasks
    },
    TaskStatus.REVIEW: {
        TaskStatus.COMPLETED,
        TaskStatus.WORKING,  # Needs more work
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.BLOCKED: {
        TaskStatus.PENDING,
        TaskStatus.ASSIGNED,
        TaskStatus.WORKING,
        TaskStatus.CANCELLED,
        TaskStatus.FAILED,
    },
    TaskStatus.COMPLETED: set(),  # Terminal state
    TaskStatus.FAILED: {TaskStatus.PENDING},  # Can retry
    TaskStatus.CANCELLED: set(),  # Terminal state
}


@dataclass
class TaskHistoryEntry:
    """Records a state change or action in task history.

    Attributes:
        timestamp: When the event occurred
        from_status: Previous status (None if creation)
        to_status: New status
        agent_id: Agent that made the change
        message: Description of the change
        metadata: Additional data about the change
    """

    timestamp: str
    from_status: str | None
    to_status: str
    agent_id: str
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskHistoryEntry:
        """Create from dictionary."""
        return cls(**data)


@dataclass
class Task:
    """Represents a delegatable task.

    Attributes:
        task_id: Unique task identifier
        objective: What the task should accomplish
        status: Current lifecycle state
        priority: Task priority level
        created_by: Agent that created the task
        assigned_to: Agent currently assigned (None if unassigned)
        context_id: ID for grouping related tasks
        constraints: List of constraints for the task
        files: List of files relevant to the task
        blocked_by: Task IDs that block this task
        blocks: Task IDs that this task blocks
        result: Result data when completed
        error: Error information if failed
        history: List of state changes
        metadata: Additional task data
        created_at: Creation timestamp
        updated_at: Last update timestamp
        parent_task_id: Parent task for subtasks
    """

    task_id: str
    objective: str
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.NORMAL
    created_by: str = ""
    assigned_to: str | None = None
    context_id: str | None = None
    constraints: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None
    history: list[TaskHistoryEntry] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    parent_task_id: str | None = None

    def __post_init__(self):
        """Handle type conversions."""
        if isinstance(self.status, str):
            self.status = TaskStatus(self.status)
        if isinstance(self.priority, str):
            self.priority = TaskPriority(self.priority)

    def can_transition_to(self, new_status: TaskStatus) -> bool:
        """Check if transition to new status is valid.

        Args:
            new_status: Target status

        Returns:
            True if transition is allowed
        """
        return new_status in VALID_TRANSITIONS.get(self.status, set())

    def transition_to(
        self,
        new_status: TaskStatus,
        agent_id: str,
        message: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Transition task to a new status.

        Args:
            new_status: Target status
            agent_id: Agent making the transition
            message: Reason for transition
            metadata: Additional data

        Raises:
            InvalidTransitionError: If transition is not allowed
        """
        if not self.can_transition_to(new_status):
            raise InvalidTransitionError(
                f"Cannot transition from {self.status.value} to {new_status.value}"
            )

        # Record history
        entry = TaskHistoryEntry(
            timestamp=datetime.now(UTC).isoformat(),
            from_status=self.status.value,
            to_status=new_status.value,
            agent_id=agent_id,
            message=message,
            metadata=metadata or {},
        )
        self.history.append(entry)

        # Update status
        old_status = self.status
        self.status = new_status
        self.updated_at = datetime.now(UTC).isoformat()

        logger.debug(
            f"Task {self.task_id}: {old_status.value} -> {new_status.value} by {agent_id}"
        )

    def assign_to(self, agent_id: str, message: str = "") -> None:
        """Assign task to an agent.

        Args:
            agent_id: Agent to assign to
            message: Optional message
        """
        self.assigned_to = agent_id
        if self.status == TaskStatus.PENDING:
            self.transition_to(TaskStatus.ASSIGNED, agent_id, message)
        self.updated_at = datetime.now(UTC).isoformat()

    def start_work(self, agent_id: str, message: str = "") -> None:
        """Mark task as being worked on.

        Args:
            agent_id: Agent starting work
            message: Optional message
        """
        self.transition_to(TaskStatus.WORKING, agent_id, message)

    def submit_for_review(self, agent_id: str, message: str = "") -> None:
        """Submit task for review.

        Args:
            agent_id: Agent submitting
            message: Optional message about the work done
        """
        self.transition_to(TaskStatus.REVIEW, agent_id, message)

    def complete(
        self,
        agent_id: str,
        result: dict[str, Any] | None = None,
        message: str = "",
    ) -> None:
        """Mark task as completed.

        Args:
            agent_id: Agent completing the task
            result: Result data
            message: Completion message
        """
        self.result = result
        self.transition_to(TaskStatus.COMPLETED, agent_id, message, {"result": result})

    def fail(self, agent_id: str, error: str, message: str = "") -> None:
        """Mark task as failed.

        Args:
            agent_id: Agent reporting failure
            error: Error description
            message: Additional context
        """
        self.error = error
        self.transition_to(TaskStatus.FAILED, agent_id, message, {"error": error})

    def block(self, agent_id: str, blocked_by: list[str], message: str = "") -> None:
        """Mark task as blocked.

        Args:
            agent_id: Agent reporting block
            blocked_by: Task IDs causing the block
            message: Block reason
        """
        self.blocked_by.extend(blocked_by)
        self.transition_to(TaskStatus.BLOCKED, agent_id, message, {"blocked_by": blocked_by})

    def unblock(self, agent_id: str, message: str = "") -> None:
        """Unblock task and return to previous working state.

        Args:
            agent_id: Agent unblocking
            message: Unblock message
        """
        self.blocked_by = []
        # Return to assigned if we have an assignee, otherwise pending
        target = TaskStatus.ASSIGNED if self.assigned_to else TaskStatus.PENDING
        self.transition_to(target, agent_id, message)

    def cancel(self, agent_id: str, message: str = "") -> None:
        """Cancel the task.

        Args:
            agent_id: Agent cancelling
            message: Cancellation reason
        """
        self.transition_to(TaskStatus.CANCELLED, agent_id, message)

    def is_terminal(self) -> bool:
        """Check if task is in a terminal state.

        Returns:
            True if completed, failed, or cancelled
        """
        return self.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)

    def is_active(self) -> bool:
        """Check if task is actively being worked on.

        Returns:
            True if assigned, working, or in review
        """
        return self.status in (TaskStatus.ASSIGNED, TaskStatus.WORKING, TaskStatus.REVIEW)

    def to_dict(self) -> dict[str, Any]:
        """Convert task to dictionary for JSON serialization."""
        data = asdict(self)
        data["status"] = self.status.value
        data["priority"] = self.priority.value
        data["history"] = [h.to_dict() if isinstance(h, TaskHistoryEntry) else h for h in self.history]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Task:
        """Create Task from dictionary."""
        # Convert history entries
        history = []
        for entry in data.get("history", []):
            if isinstance(entry, dict):
                history.append(TaskHistoryEntry.from_dict(entry))
            else:
                history.append(entry)
        data["history"] = history

        return cls(**data)


def get_tasks_path(project_root: Path | None = None) -> Path:
    """Get the path to the tasks file.

    Args:
        project_root: Optional project root directory

    Returns:
        Path to TASKS.json in project root
    """
    root = get_project_root(project_root)
    return root / TASKS_FILENAME


class TaskManager:
    """Manages task lifecycle and persistence.

    Provides thread-safe operations for creating, updating,
    and querying tasks with file-based persistence.
    """

    def __init__(self, project_root: Path | None = None):
        """Initialize the task manager.

        Args:
            project_root: Root directory of the project
        """
        self.project_root = get_project_root(project_root)
        self.tasks_path = get_tasks_path(self.project_root)
        self._lock = threading.Lock()

    def _read_tasks(self) -> dict[str, Task]:
        """Read all tasks from file with locking.

        Returns:
            Dictionary mapping task_id to Task
        """
        if not self.tasks_path.exists():
            return {}

        try:
            with FileLock(self.tasks_path, timeout=TASK_LOCK_TIMEOUT_SECONDS, shared=True):
                with open(self.tasks_path, encoding="utf-8") as f:
                    data = json.load(f)

                tasks = {}
                for task_id, task_data in data.get("tasks", {}).items():
                    try:
                        tasks[task_id] = Task.from_dict(task_data)
                    except Exception as e:
                        logger.warning(f"Invalid task {task_id}: {e}")
                        continue

                return tasks

        except FileLockTimeout:
            logger.error(f"Timeout acquiring lock on {self.tasks_path}")
            return {}
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Invalid JSON in tasks file: {e}")
            return {}
        except Exception as e:
            logger.error(f"Error reading tasks file: {e}")
            return {}

    def _write_tasks(self, tasks: dict[str, Task]) -> None:
        """Write all tasks to file with locking.

        Args:
            tasks: Dictionary mapping task_id to Task
        """
        self.tasks_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "version": "1.0",
            "updated_at": datetime.now(UTC).isoformat(),
            "tasks": {task_id: task.to_dict() for task_id, task in tasks.items()},
        }

        try:
            with FileLock(self.tasks_path, timeout=TASK_LOCK_TIMEOUT_SECONDS, shared=False):
                temp_path = self.tasks_path.with_suffix(".json.tmp")
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)

                temp_path.replace(self.tasks_path)

        except FileLockTimeout:
            logger.error(f"Timeout acquiring write lock on {self.tasks_path}")
            raise
        except Exception as e:
            logger.error(f"Error writing tasks file: {e}")
            raise

    def create_task(
        self,
        objective: str,
        created_by: str,
        priority: TaskPriority = TaskPriority.NORMAL,
        context_id: str | None = None,
        constraints: list[str] | None = None,
        files: list[str] | None = None,
        parent_task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Task:
        """Create a new task.

        Args:
            objective: Task objective
            created_by: Agent creating the task
            priority: Task priority
            context_id: Context for grouping
            constraints: Task constraints
            files: Relevant files
            parent_task_id: Parent task ID for subtasks
            metadata: Additional metadata

        Returns:
            Created Task
        """
        task_id = str(uuid.uuid4())

        task = Task(
            task_id=task_id,
            objective=objective,
            created_by=created_by,
            priority=priority,
            context_id=context_id,
            constraints=constraints or [],
            files=files or [],
            parent_task_id=parent_task_id,
            metadata=metadata or {},
        )

        # Add creation to history
        task.history.append(
            TaskHistoryEntry(
                timestamp=task.created_at,
                from_status=None,
                to_status=TaskStatus.PENDING.value,
                agent_id=created_by,
                message="Task created",
            )
        )

        with self._lock:
            tasks = self._read_tasks()
            tasks[task_id] = task
            self._write_tasks(tasks)

        logger.info(f"Created task {task_id}: {objective[:50]}...")
        return task

    def get_task(self, task_id: str) -> Task | None:
        """Get a task by ID.

        Args:
            task_id: Task identifier

        Returns:
            Task if found, None otherwise
        """
        tasks = self._read_tasks()
        return tasks.get(task_id)

    def update_task(self, task: Task) -> None:
        """Update a task.

        Args:
            task: Task to update

        Raises:
            TaskNotFoundError: If task not found
        """
        with self._lock:
            tasks = self._read_tasks()

            if task.task_id not in tasks:
                raise TaskNotFoundError(f"Task not found: {task.task_id}")

            task.updated_at = datetime.now(UTC).isoformat()
            tasks[task.task_id] = task
            self._write_tasks(tasks)

    def delete_task(self, task_id: str) -> bool:
        """Delete a task.

        Args:
            task_id: Task identifier

        Returns:
            True if deleted, False if not found
        """
        with self._lock:
            tasks = self._read_tasks()

            if task_id not in tasks:
                return False

            del tasks[task_id]
            self._write_tasks(tasks)

        logger.info(f"Deleted task {task_id}")
        return True

    def list_tasks(
        self,
        status: TaskStatus | None = None,
        assigned_to: str | None = None,
        created_by: str | None = None,
        context_id: str | None = None,
        priority: TaskPriority | None = None,
        include_terminal: bool = False,
    ) -> list[Task]:
        """List tasks with optional filtering.

        Args:
            status: Filter by status
            assigned_to: Filter by assignee
            created_by: Filter by creator
            context_id: Filter by context
            priority: Filter by priority
            include_terminal: Include completed/failed/cancelled tasks

        Returns:
            List of matching tasks
        """
        tasks = self._read_tasks()
        result = list(tasks.values())

        if status is not None:
            result = [t for t in result if t.status == status]

        if assigned_to is not None:
            result = [t for t in result if t.assigned_to == assigned_to]

        if created_by is not None:
            result = [t for t in result if t.created_by == created_by]

        if context_id is not None:
            result = [t for t in result if t.context_id == context_id]

        if priority is not None:
            result = [t for t in result if t.priority == priority]

        if not include_terminal:
            result = [t for t in result if not t.is_terminal()]

        # Sort by priority (critical first) then by creation time
        priority_order = {
            TaskPriority.CRITICAL: 0,
            TaskPriority.HIGH: 1,
            TaskPriority.NORMAL: 2,
            TaskPriority.LOW: 3,
        }
        result.sort(key=lambda t: (priority_order[t.priority], t.created_at))

        return result

    def get_pending_tasks(self) -> list[Task]:
        """Get all pending (unassigned) tasks.

        Returns:
            List of pending tasks
        """
        return self.list_tasks(status=TaskStatus.PENDING)

    def get_agent_tasks(self, agent_id: str, include_terminal: bool = False) -> list[Task]:
        """Get all tasks assigned to an agent.

        Args:
            agent_id: Agent identifier
            include_terminal: Include completed/failed tasks

        Returns:
            List of tasks assigned to the agent
        """
        return self.list_tasks(assigned_to=agent_id, include_terminal=include_terminal)

    def get_blocked_tasks(self) -> list[Task]:
        """Get all blocked tasks.

        Returns:
            List of blocked tasks
        """
        return self.list_tasks(status=TaskStatus.BLOCKED)

    def get_tasks_in_review(self) -> list[Task]:
        """Get all tasks awaiting review.

        Returns:
            List of tasks in review status
        """
        return self.list_tasks(status=TaskStatus.REVIEW)

    def assign_task(
        self,
        task_id: str,
        agent_id: str,
        message: str = "",
    ) -> Task:
        """Assign a task to an agent.

        Args:
            task_id: Task identifier
            agent_id: Agent to assign to
            message: Optional message

        Returns:
            Updated task

        Raises:
            TaskNotFoundError: If task not found
        """
        with self._lock:
            tasks = self._read_tasks()

            if task_id not in tasks:
                raise TaskNotFoundError(f"Task not found: {task_id}")

            task = tasks[task_id]
            task.assign_to(agent_id, message)
            self._write_tasks(tasks)

        logger.info(f"Assigned task {task_id} to {agent_id}")
        return task

    def transition_task(
        self,
        task_id: str,
        new_status: TaskStatus,
        agent_id: str,
        message: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Task:
        """Transition a task to a new status.

        Args:
            task_id: Task identifier
            new_status: Target status
            agent_id: Agent making the transition
            message: Transition message
            metadata: Additional metadata

        Returns:
            Updated task

        Raises:
            TaskNotFoundError: If task not found
            InvalidTransitionError: If transition is invalid
        """
        with self._lock:
            tasks = self._read_tasks()

            if task_id not in tasks:
                raise TaskNotFoundError(f"Task not found: {task_id}")

            task = tasks[task_id]
            task.transition_to(new_status, agent_id, message, metadata)
            self._write_tasks(tasks)

        return task

    def complete_task(
        self,
        task_id: str,
        agent_id: str,
        result: dict[str, Any] | None = None,
        message: str = "",
    ) -> Task:
        """Complete a task.

        Args:
            task_id: Task identifier
            agent_id: Agent completing the task
            result: Result data
            message: Completion message

        Returns:
            Updated task
        """
        with self._lock:
            tasks = self._read_tasks()

            if task_id not in tasks:
                raise TaskNotFoundError(f"Task not found: {task_id}")

            task = tasks[task_id]
            task.complete(agent_id, result, message)
            self._write_tasks(tasks)

        logger.info(f"Task {task_id} completed by {agent_id}")
        return task

    def fail_task(
        self,
        task_id: str,
        agent_id: str,
        error: str,
        message: str = "",
    ) -> Task:
        """Mark a task as failed.

        Args:
            task_id: Task identifier
            agent_id: Agent reporting failure
            error: Error description
            message: Additional context

        Returns:
            Updated task
        """
        with self._lock:
            tasks = self._read_tasks()

            if task_id not in tasks:
                raise TaskNotFoundError(f"Task not found: {task_id}")

            task = tasks[task_id]
            task.fail(agent_id, error, message)
            self._write_tasks(tasks)

        logger.warning(f"Task {task_id} failed: {error}")
        return task

    def get_context_tasks(self, context_id: str) -> list[Task]:
        """Get all tasks for a context.

        Args:
            context_id: Context identifier

        Returns:
            List of tasks in the context
        """
        return self.list_tasks(context_id=context_id, include_terminal=True)

    def get_subtasks(self, parent_task_id: str) -> list[Task]:
        """Get subtasks of a parent task.

        Args:
            parent_task_id: Parent task identifier

        Returns:
            List of subtasks
        """
        tasks = self._read_tasks()
        return [t for t in tasks.values() if t.parent_task_id == parent_task_id]

    def get_task_stats(self) -> dict[str, int]:
        """Get task statistics.

        Returns:
            Dictionary with counts per status
        """
        tasks = self._read_tasks()
        stats = {status.value: 0 for status in TaskStatus}

        for task in tasks.values():
            stats[task.status.value] += 1

        stats["total"] = len(tasks)
        return stats
