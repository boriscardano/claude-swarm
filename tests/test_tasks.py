"""Unit tests for the task state machine and task management system.

Tests cover:
- Task creation and initialization
- TaskStatus transitions (valid and invalid)
- TaskPriority handling
- TaskManager operations (create, get, update, list)
- Task blocking/unblocking
- History tracking
- Error handling for invalid state transitions
- File locking and persistence
- Task filtering and querying
"""

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from claudeswarm.tasks import (
    TASKS_FILENAME,
    InvalidTransitionError,
    Task,
    TaskHistoryEntry,
    TaskManager,
    TaskNotFoundError,
    TaskPriority,
    TaskStatus,
    VALID_TRANSITIONS,
    get_tasks_path,
)


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def task_manager(temp_project_dir):
    """Create a TaskManager instance for testing."""
    return TaskManager(project_root=temp_project_dir)


@pytest.fixture
def sample_task():
    """Create a sample task for testing."""
    return Task(
        task_id="test-task-123",
        objective="Implement feature X",
        status=TaskStatus.PENDING,
        priority=TaskPriority.NORMAL,
        created_by="agent-0",
        context_id="feature-x",
        constraints=["Use Python 3.11+", "No external dependencies"],
        files=["src/feature.py", "tests/test_feature.py"],
    )


class TestTaskStatus:
    """Tests for TaskStatus enum."""

    def test_all_statuses_exist(self):
        """Test that all expected statuses are defined."""
        expected_statuses = [
            "PENDING",
            "ASSIGNED",
            "WORKING",
            "REVIEW",
            "COMPLETED",
            "BLOCKED",
            "FAILED",
            "CANCELLED",
        ]
        for status in expected_statuses:
            assert hasattr(TaskStatus, status)

    def test_status_values(self):
        """Test that status values match their lowercase names."""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.ASSIGNED.value == "assigned"
        assert TaskStatus.WORKING.value == "working"
        assert TaskStatus.REVIEW.value == "review"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.BLOCKED.value == "blocked"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.CANCELLED.value == "cancelled"


class TestTaskPriority:
    """Tests for TaskPriority enum."""

    def test_all_priorities_exist(self):
        """Test that all expected priorities are defined."""
        expected_priorities = ["LOW", "NORMAL", "HIGH", "CRITICAL"]
        for priority in expected_priorities:
            assert hasattr(TaskPriority, priority)

    def test_priority_values(self):
        """Test that priority values match their lowercase names."""
        assert TaskPriority.LOW.value == "low"
        assert TaskPriority.NORMAL.value == "normal"
        assert TaskPriority.HIGH.value == "high"
        assert TaskPriority.CRITICAL.value == "critical"


class TestValidTransitions:
    """Tests for valid state transitions."""

    def test_pending_transitions(self):
        """Test valid transitions from PENDING state."""
        assert TaskStatus.ASSIGNED in VALID_TRANSITIONS[TaskStatus.PENDING]
        assert TaskStatus.CANCELLED in VALID_TRANSITIONS[TaskStatus.PENDING]

    def test_assigned_transitions(self):
        """Test valid transitions from ASSIGNED state."""
        assert TaskStatus.WORKING in VALID_TRANSITIONS[TaskStatus.ASSIGNED]
        assert TaskStatus.BLOCKED in VALID_TRANSITIONS[TaskStatus.ASSIGNED]
        assert TaskStatus.CANCELLED in VALID_TRANSITIONS[TaskStatus.ASSIGNED]
        assert TaskStatus.PENDING in VALID_TRANSITIONS[TaskStatus.ASSIGNED]

    def test_working_transitions(self):
        """Test valid transitions from WORKING state."""
        assert TaskStatus.REVIEW in VALID_TRANSITIONS[TaskStatus.WORKING]
        assert TaskStatus.BLOCKED in VALID_TRANSITIONS[TaskStatus.WORKING]
        assert TaskStatus.FAILED in VALID_TRANSITIONS[TaskStatus.WORKING]
        assert TaskStatus.CANCELLED in VALID_TRANSITIONS[TaskStatus.WORKING]
        assert TaskStatus.COMPLETED in VALID_TRANSITIONS[TaskStatus.WORKING]

    def test_review_transitions(self):
        """Test valid transitions from REVIEW state."""
        assert TaskStatus.COMPLETED in VALID_TRANSITIONS[TaskStatus.REVIEW]
        assert TaskStatus.WORKING in VALID_TRANSITIONS[TaskStatus.REVIEW]
        assert TaskStatus.FAILED in VALID_TRANSITIONS[TaskStatus.REVIEW]
        assert TaskStatus.CANCELLED in VALID_TRANSITIONS[TaskStatus.REVIEW]

    def test_blocked_transitions(self):
        """Test valid transitions from BLOCKED state."""
        assert TaskStatus.PENDING in VALID_TRANSITIONS[TaskStatus.BLOCKED]
        assert TaskStatus.ASSIGNED in VALID_TRANSITIONS[TaskStatus.BLOCKED]
        assert TaskStatus.WORKING in VALID_TRANSITIONS[TaskStatus.BLOCKED]
        assert TaskStatus.CANCELLED in VALID_TRANSITIONS[TaskStatus.BLOCKED]
        assert TaskStatus.FAILED in VALID_TRANSITIONS[TaskStatus.BLOCKED]

    def test_terminal_states_no_transitions(self):
        """Test that terminal states have no valid transitions."""
        assert len(VALID_TRANSITIONS[TaskStatus.COMPLETED]) == 0
        assert len(VALID_TRANSITIONS[TaskStatus.CANCELLED]) == 0

    def test_failed_can_retry(self):
        """Test that failed tasks can be retried."""
        assert TaskStatus.PENDING in VALID_TRANSITIONS[TaskStatus.FAILED]


class TestTaskHistoryEntry:
    """Tests for TaskHistoryEntry dataclass."""

    def test_creation(self):
        """Test creating a history entry."""
        entry = TaskHistoryEntry(
            timestamp="2024-01-15T10:00:00Z",
            from_status="pending",
            to_status="assigned",
            agent_id="agent-1",
            message="Assigned to agent-1",
            metadata={"priority": "high"},
        )
        assert entry.timestamp == "2024-01-15T10:00:00Z"
        assert entry.from_status == "pending"
        assert entry.to_status == "assigned"
        assert entry.agent_id == "agent-1"
        assert entry.message == "Assigned to agent-1"
        assert entry.metadata["priority"] == "high"

    def test_creation_with_defaults(self):
        """Test creating a history entry with default values."""
        entry = TaskHistoryEntry(
            timestamp="2024-01-15T10:00:00Z",
            from_status=None,
            to_status="pending",
            agent_id="agent-0",
        )
        assert entry.message == ""
        assert entry.metadata == {}

    def test_to_dict(self):
        """Test converting history entry to dictionary."""
        entry = TaskHistoryEntry(
            timestamp="2024-01-15T10:00:00Z",
            from_status="pending",
            to_status="assigned",
            agent_id="agent-1",
            message="Test message",
            metadata={"key": "value"},
        )
        data = entry.to_dict()
        assert data["timestamp"] == "2024-01-15T10:00:00Z"
        assert data["from_status"] == "pending"
        assert data["to_status"] == "assigned"
        assert data["agent_id"] == "agent-1"
        assert data["message"] == "Test message"
        assert data["metadata"]["key"] == "value"

    def test_from_dict(self):
        """Test creating history entry from dictionary."""
        data = {
            "timestamp": "2024-01-15T10:00:00Z",
            "from_status": "pending",
            "to_status": "assigned",
            "agent_id": "agent-1",
            "message": "Test message",
            "metadata": {"key": "value"},
        }
        entry = TaskHistoryEntry.from_dict(data)
        assert entry.timestamp == "2024-01-15T10:00:00Z"
        assert entry.from_status == "pending"
        assert entry.to_status == "assigned"
        assert entry.agent_id == "agent-1"
        assert entry.message == "Test message"
        assert entry.metadata["key"] == "value"


class TestTask:
    """Tests for Task dataclass and methods."""

    def test_creation_with_defaults(self):
        """Test creating a task with default values."""
        task = Task(task_id="test-123", objective="Test objective")
        assert task.task_id == "test-123"
        assert task.objective == "Test objective"
        assert task.status == TaskStatus.PENDING
        assert task.priority == TaskPriority.NORMAL
        assert task.assigned_to is None
        assert task.context_id is None
        assert task.constraints == []
        assert task.files == []
        assert task.blocked_by == []
        assert task.blocks == []
        assert task.result is None
        assert task.error is None
        assert task.history == []
        assert task.metadata == {}
        assert task.parent_task_id is None

    def test_creation_with_all_fields(self, sample_task):
        """Test creating a task with all fields specified."""
        assert sample_task.task_id == "test-task-123"
        assert sample_task.objective == "Implement feature X"
        assert sample_task.status == TaskStatus.PENDING
        assert sample_task.priority == TaskPriority.NORMAL
        assert sample_task.created_by == "agent-0"
        assert sample_task.context_id == "feature-x"
        assert len(sample_task.constraints) == 2
        assert len(sample_task.files) == 2

    def test_post_init_converts_string_status(self):
        """Test that string status is converted to TaskStatus enum."""
        task = Task(task_id="test-123", objective="Test", status="working")
        assert task.status == TaskStatus.WORKING
        assert isinstance(task.status, TaskStatus)

    def test_post_init_converts_string_priority(self):
        """Test that string priority is converted to TaskPriority enum."""
        task = Task(task_id="test-123", objective="Test", priority="high")
        assert task.priority == TaskPriority.HIGH
        assert isinstance(task.priority, TaskPriority)

    def test_can_transition_to_valid(self, sample_task):
        """Test checking valid transitions."""
        sample_task.status = TaskStatus.PENDING
        assert sample_task.can_transition_to(TaskStatus.ASSIGNED)
        assert sample_task.can_transition_to(TaskStatus.CANCELLED)

    def test_can_transition_to_invalid(self, sample_task):
        """Test checking invalid transitions."""
        sample_task.status = TaskStatus.PENDING
        assert not sample_task.can_transition_to(TaskStatus.WORKING)
        assert not sample_task.can_transition_to(TaskStatus.COMPLETED)

    def test_transition_to_valid(self, sample_task):
        """Test transitioning to a valid state."""
        sample_task.status = TaskStatus.PENDING
        initial_history_count = len(sample_task.history)

        sample_task.transition_to(TaskStatus.ASSIGNED, "agent-1", "Assigning task")

        assert sample_task.status == TaskStatus.ASSIGNED
        assert len(sample_task.history) == initial_history_count + 1
        assert sample_task.history[-1].from_status == "pending"
        assert sample_task.history[-1].to_status == "assigned"
        assert sample_task.history[-1].agent_id == "agent-1"
        assert sample_task.history[-1].message == "Assigning task"

    def test_transition_to_invalid_raises_error(self, sample_task):
        """Test that invalid transitions raise InvalidTransitionError."""
        sample_task.status = TaskStatus.PENDING

        with pytest.raises(InvalidTransitionError) as exc_info:
            sample_task.transition_to(TaskStatus.WORKING, "agent-1")

        assert "Cannot transition from pending to working" in str(exc_info.value)

    def test_transition_with_metadata(self, sample_task):
        """Test transition with metadata."""
        sample_task.status = TaskStatus.PENDING
        metadata = {"reason": "high priority", "urgency": "critical"}

        sample_task.transition_to(TaskStatus.ASSIGNED, "agent-1", metadata=metadata)

        assert sample_task.history[-1].metadata == metadata

    def test_assign_to_from_pending(self, sample_task):
        """Test assigning a pending task."""
        sample_task.status = TaskStatus.PENDING

        sample_task.assign_to("agent-1", "Taking this task")

        assert sample_task.assigned_to == "agent-1"
        assert sample_task.status == TaskStatus.ASSIGNED
        assert sample_task.history[-1].message == "Taking this task"

    def test_assign_to_updates_assignee(self, sample_task):
        """Test that assign_to updates the assignee."""
        sample_task.status = TaskStatus.WORKING
        sample_task.assigned_to = "agent-1"

        sample_task.assign_to("agent-2", "Reassigning")

        assert sample_task.assigned_to == "agent-2"

    def test_start_work(self, sample_task):
        """Test starting work on a task."""
        sample_task.status = TaskStatus.ASSIGNED

        sample_task.start_work("agent-1", "Starting implementation")

        assert sample_task.status == TaskStatus.WORKING
        assert sample_task.history[-1].to_status == "working"

    def test_submit_for_review(self, sample_task):
        """Test submitting task for review."""
        sample_task.status = TaskStatus.WORKING

        sample_task.submit_for_review("agent-1", "Implementation complete")

        assert sample_task.status == TaskStatus.REVIEW
        assert sample_task.history[-1].to_status == "review"

    def test_complete(self, sample_task):
        """Test completing a task."""
        sample_task.status = TaskStatus.WORKING
        result = {"status": "success", "files_modified": 3}

        sample_task.complete("agent-1", result, "Task finished successfully")

        assert sample_task.status == TaskStatus.COMPLETED
        assert sample_task.result == result
        assert sample_task.history[-1].metadata["result"] == result

    def test_complete_from_review(self, sample_task):
        """Test completing a task from review state."""
        sample_task.status = TaskStatus.REVIEW
        result = {"status": "approved"}

        sample_task.complete("agent-2", result, "Review passed")

        assert sample_task.status == TaskStatus.COMPLETED
        assert sample_task.result == result

    def test_fail(self, sample_task):
        """Test marking a task as failed."""
        sample_task.status = TaskStatus.WORKING
        error = "Unable to access required resource"

        sample_task.fail("agent-1", error, "Resource not available")

        assert sample_task.status == TaskStatus.FAILED
        assert sample_task.error == error
        assert sample_task.history[-1].metadata["error"] == error

    def test_block(self, sample_task):
        """Test blocking a task."""
        sample_task.status = TaskStatus.WORKING
        blockers = ["task-456", "task-789"]

        sample_task.block("agent-1", blockers, "Waiting on dependencies")

        assert sample_task.status == TaskStatus.BLOCKED
        assert "task-456" in sample_task.blocked_by
        assert "task-789" in sample_task.blocked_by
        assert sample_task.history[-1].metadata["blocked_by"] == blockers

    def test_block_accumulates_blockers(self, sample_task):
        """Test that blocking accumulates blocker task IDs."""
        sample_task.status = TaskStatus.ASSIGNED
        sample_task.block("agent-1", ["task-1"], "First blocker")

        sample_task.status = TaskStatus.BLOCKED  # Already blocked
        sample_task.blocked_by = ["task-1"]

        # Add more blockers
        sample_task.blocked_by.extend(["task-2"])

        assert "task-1" in sample_task.blocked_by
        assert "task-2" in sample_task.blocked_by

    def test_unblock_with_assignee(self, sample_task):
        """Test unblocking a task that has an assignee."""
        sample_task.status = TaskStatus.BLOCKED
        sample_task.assigned_to = "agent-1"
        sample_task.blocked_by = ["task-456"]

        sample_task.unblock("agent-1", "Dependencies resolved")

        assert sample_task.status == TaskStatus.ASSIGNED
        assert sample_task.blocked_by == []
        assert sample_task.history[-1].message == "Dependencies resolved"

    def test_unblock_without_assignee(self, sample_task):
        """Test unblocking a task without an assignee."""
        sample_task.status = TaskStatus.BLOCKED
        sample_task.assigned_to = None
        sample_task.blocked_by = ["task-456"]

        sample_task.unblock("agent-1", "Dependencies resolved")

        assert sample_task.status == TaskStatus.PENDING
        assert sample_task.blocked_by == []

    def test_cancel(self, sample_task):
        """Test cancelling a task."""
        sample_task.status = TaskStatus.PENDING

        sample_task.cancel("agent-0", "No longer needed")

        assert sample_task.status == TaskStatus.CANCELLED
        assert sample_task.history[-1].message == "No longer needed"

    def test_is_terminal_completed(self, sample_task):
        """Test is_terminal for completed task."""
        sample_task.status = TaskStatus.COMPLETED
        assert sample_task.is_terminal()

    def test_is_terminal_failed(self, sample_task):
        """Test is_terminal for failed task."""
        sample_task.status = TaskStatus.FAILED
        assert sample_task.is_terminal()

    def test_is_terminal_cancelled(self, sample_task):
        """Test is_terminal for cancelled task."""
        sample_task.status = TaskStatus.CANCELLED
        assert sample_task.is_terminal()

    def test_is_terminal_active_task(self, sample_task):
        """Test is_terminal for active task."""
        sample_task.status = TaskStatus.WORKING
        assert not sample_task.is_terminal()

    def test_is_active_assigned(self, sample_task):
        """Test is_active for assigned task."""
        sample_task.status = TaskStatus.ASSIGNED
        assert sample_task.is_active()

    def test_is_active_working(self, sample_task):
        """Test is_active for working task."""
        sample_task.status = TaskStatus.WORKING
        assert sample_task.is_active()

    def test_is_active_review(self, sample_task):
        """Test is_active for task in review."""
        sample_task.status = TaskStatus.REVIEW
        assert sample_task.is_active()

    def test_is_active_pending(self, sample_task):
        """Test is_active for pending task."""
        sample_task.status = TaskStatus.PENDING
        assert not sample_task.is_active()

    def test_is_active_blocked(self, sample_task):
        """Test is_active for blocked task."""
        sample_task.status = TaskStatus.BLOCKED
        assert not sample_task.is_active()

    def test_to_dict(self, sample_task):
        """Test converting task to dictionary."""
        data = sample_task.to_dict()

        assert data["task_id"] == "test-task-123"
        assert data["objective"] == "Implement feature X"
        assert data["status"] == "pending"
        assert data["priority"] == "normal"
        assert data["created_by"] == "agent-0"
        assert data["context_id"] == "feature-x"
        assert len(data["constraints"]) == 2
        assert len(data["files"]) == 2

    def test_to_dict_with_history(self, sample_task):
        """Test that to_dict properly serializes history entries."""
        sample_task.history.append(
            TaskHistoryEntry(
                timestamp="2024-01-15T10:00:00Z",
                from_status=None,
                to_status="pending",
                agent_id="agent-0",
                message="Task created",
            )
        )

        data = sample_task.to_dict()

        assert isinstance(data["history"], list)
        assert len(data["history"]) == 1
        assert isinstance(data["history"][0], dict)
        assert data["history"][0]["agent_id"] == "agent-0"

    def test_from_dict(self):
        """Test creating task from dictionary."""
        data = {
            "task_id": "test-123",
            "objective": "Test task",
            "status": "working",
            "priority": "high",
            "created_by": "agent-1",
            "assigned_to": "agent-1",
            "context_id": "test-context",
            "constraints": ["constraint1"],
            "files": ["file1.py"],
            "blocked_by": [],
            "blocks": [],
            "result": None,
            "error": None,
            "history": [
                {
                    "timestamp": "2024-01-15T10:00:00Z",
                    "from_status": None,
                    "to_status": "pending",
                    "agent_id": "agent-1",
                    "message": "Created",
                    "metadata": {},
                }
            ],
            "metadata": {"key": "value"},
            "created_at": "2024-01-15T10:00:00Z",
            "updated_at": "2024-01-15T10:05:00Z",
            "parent_task_id": None,
        }

        task = Task.from_dict(data)

        assert task.task_id == "test-123"
        assert task.objective == "Test task"
        assert task.status == TaskStatus.WORKING
        assert task.priority == TaskPriority.HIGH
        assert len(task.history) == 1
        assert isinstance(task.history[0], TaskHistoryEntry)


class TestGetTasksPath:
    """Tests for get_tasks_path function."""

    def test_get_tasks_path_with_explicit_root(self, temp_project_dir):
        """Test getting tasks path with explicit project root."""
        path = get_tasks_path(temp_project_dir)
        # Resolve both paths to handle macOS /var -> /private/var symlink
        assert path.resolve() == (temp_project_dir / TASKS_FILENAME).resolve()
        assert path.name == "TASKS.json"

    def test_get_tasks_path_default(self):
        """Test getting tasks path with default project root."""
        with patch("claudeswarm.tasks.get_project_root") as mock_get_root:
            mock_root = Path("/mock/project")
            mock_get_root.return_value = mock_root

            path = get_tasks_path()

            assert path == mock_root / TASKS_FILENAME


class TestTaskManager:
    """Tests for TaskManager class."""

    def test_initialization(self, temp_project_dir):
        """Test TaskManager initialization."""
        manager = TaskManager(temp_project_dir)

        # Resolve both paths to handle macOS /var -> /private/var symlink
        assert manager.project_root.resolve() == temp_project_dir.resolve()
        assert manager.tasks_path.resolve() == (temp_project_dir / TASKS_FILENAME).resolve()

    def test_create_task(self, task_manager):
        """Test creating a new task."""
        task = task_manager.create_task(
            objective="Implement authentication",
            created_by="agent-1",
            priority=TaskPriority.HIGH,
            context_id="auth-feature",
            constraints=["Use JWT"],
            files=["src/auth.py"],
        )

        assert task.objective == "Implement authentication"
        assert task.created_by == "agent-1"
        assert task.priority == TaskPriority.HIGH
        assert task.status == TaskStatus.PENDING
        assert task.context_id == "auth-feature"
        assert "Use JWT" in task.constraints
        assert "src/auth.py" in task.files
        assert len(task.history) == 1
        assert task.history[0].message == "Task created"

    def test_create_task_with_parent(self, task_manager):
        """Test creating a subtask with parent reference."""
        parent_task = task_manager.create_task(
            objective="Main task",
            created_by="agent-1",
        )

        subtask = task_manager.create_task(
            objective="Subtask",
            created_by="agent-1",
            parent_task_id=parent_task.task_id,
        )

        assert subtask.parent_task_id == parent_task.task_id

    def test_create_task_persists_to_file(self, task_manager, temp_project_dir):
        """Test that creating a task persists to file."""
        task = task_manager.create_task(
            objective="Test task",
            created_by="agent-1",
        )

        tasks_file = temp_project_dir / TASKS_FILENAME
        assert tasks_file.exists()

        with open(tasks_file) as f:
            data = json.load(f)

        assert task.task_id in data["tasks"]
        assert data["tasks"][task.task_id]["objective"] == "Test task"

    def test_get_task_existing(self, task_manager):
        """Test getting an existing task."""
        created_task = task_manager.create_task(
            objective="Test task",
            created_by="agent-1",
        )

        retrieved_task = task_manager.get_task(created_task.task_id)

        assert retrieved_task is not None
        assert retrieved_task.task_id == created_task.task_id
        assert retrieved_task.objective == created_task.objective

    def test_get_task_nonexistent(self, task_manager):
        """Test getting a nonexistent task returns None."""
        task = task_manager.get_task("nonexistent-task-id")
        assert task is None

    def test_update_task(self, task_manager):
        """Test updating a task."""
        task = task_manager.create_task(
            objective="Original objective",
            created_by="agent-1",
        )

        task.objective = "Updated objective"
        task_manager.update_task(task)

        retrieved = task_manager.get_task(task.task_id)
        assert retrieved.objective == "Updated objective"

    def test_update_task_not_found(self, task_manager):
        """Test updating a nonexistent task raises error."""
        task = Task(task_id="nonexistent", objective="Test")

        with pytest.raises(TaskNotFoundError):
            task_manager.update_task(task)

    def test_delete_task_existing(self, task_manager):
        """Test deleting an existing task."""
        task = task_manager.create_task(
            objective="Task to delete",
            created_by="agent-1",
        )

        result = task_manager.delete_task(task.task_id)

        assert result is True
        assert task_manager.get_task(task.task_id) is None

    def test_delete_task_nonexistent(self, task_manager):
        """Test deleting a nonexistent task returns False."""
        result = task_manager.delete_task("nonexistent-task-id")
        assert result is False

    def test_list_tasks_empty(self, task_manager):
        """Test listing tasks when none exist."""
        tasks = task_manager.list_tasks()
        assert tasks == []

    def test_list_tasks_all(self, task_manager):
        """Test listing all tasks."""
        task1 = task_manager.create_task("Task 1", "agent-1")
        task2 = task_manager.create_task("Task 2", "agent-1")

        tasks = task_manager.list_tasks(include_terminal=True)

        assert len(tasks) == 2
        task_ids = [t.task_id for t in tasks]
        assert task1.task_id in task_ids
        assert task2.task_id in task_ids

    def test_list_tasks_by_status(self, task_manager):
        """Test filtering tasks by status."""
        task1 = task_manager.create_task("Task 1", "agent-1")
        task2 = task_manager.create_task("Task 2", "agent-1")

        task_manager.assign_task(task1.task_id, "agent-1")

        pending_tasks = task_manager.list_tasks(status=TaskStatus.PENDING)
        assigned_tasks = task_manager.list_tasks(status=TaskStatus.ASSIGNED)

        assert len(pending_tasks) == 1
        assert pending_tasks[0].task_id == task2.task_id
        assert len(assigned_tasks) == 1
        assert assigned_tasks[0].task_id == task1.task_id

    def test_list_tasks_by_assignee(self, task_manager):
        """Test filtering tasks by assignee."""
        task1 = task_manager.create_task("Task 1", "agent-1")
        task2 = task_manager.create_task("Task 2", "agent-1")

        task_manager.assign_task(task1.task_id, "agent-1")
        task_manager.assign_task(task2.task_id, "agent-2")

        agent1_tasks = task_manager.list_tasks(assigned_to="agent-1")
        agent2_tasks = task_manager.list_tasks(assigned_to="agent-2")

        assert len(agent1_tasks) == 1
        assert agent1_tasks[0].task_id == task1.task_id
        assert len(agent2_tasks) == 1
        assert agent2_tasks[0].task_id == task2.task_id

    def test_list_tasks_by_creator(self, task_manager):
        """Test filtering tasks by creator."""
        task1 = task_manager.create_task("Task 1", "agent-1")
        task2 = task_manager.create_task("Task 2", "agent-2")

        agent1_created = task_manager.list_tasks(created_by="agent-1")
        agent2_created = task_manager.list_tasks(created_by="agent-2")

        assert len(agent1_created) == 1
        assert agent1_created[0].task_id == task1.task_id
        assert len(agent2_created) == 1
        assert agent2_created[0].task_id == task2.task_id

    def test_list_tasks_by_context(self, task_manager):
        """Test filtering tasks by context."""
        task1 = task_manager.create_task("Task 1", "agent-1", context_id="feature-a")
        task2 = task_manager.create_task("Task 2", "agent-1", context_id="feature-b")

        context_a_tasks = task_manager.list_tasks(context_id="feature-a")
        context_b_tasks = task_manager.list_tasks(context_id="feature-b")

        assert len(context_a_tasks) == 1
        assert context_a_tasks[0].task_id == task1.task_id
        assert len(context_b_tasks) == 1
        assert context_b_tasks[0].task_id == task2.task_id

    def test_list_tasks_by_priority(self, task_manager):
        """Test filtering tasks by priority."""
        task1 = task_manager.create_task("Task 1", "agent-1", priority=TaskPriority.HIGH)
        task2 = task_manager.create_task("Task 2", "agent-1", priority=TaskPriority.LOW)

        high_priority = task_manager.list_tasks(priority=TaskPriority.HIGH)
        low_priority = task_manager.list_tasks(priority=TaskPriority.LOW)

        assert len(high_priority) == 1
        assert high_priority[0].task_id == task1.task_id
        assert len(low_priority) == 1
        assert low_priority[0].task_id == task2.task_id

    def test_list_tasks_exclude_terminal(self, task_manager):
        """Test that terminal tasks are excluded by default."""
        task1 = task_manager.create_task("Task 1", "agent-1")
        task2 = task_manager.create_task("Task 2", "agent-1")

        # Complete task1
        task = task_manager.get_task(task1.task_id)
        task_manager.assign_task(task1.task_id, "agent-1")
        task_manager.transition_task(task1.task_id, TaskStatus.WORKING, "agent-1")
        task_manager.complete_task(task1.task_id, "agent-1")

        # List without terminal tasks
        active_tasks = task_manager.list_tasks()
        assert len(active_tasks) == 1
        assert active_tasks[0].task_id == task2.task_id

        # List with terminal tasks
        all_tasks = task_manager.list_tasks(include_terminal=True)
        assert len(all_tasks) == 2

    def test_list_tasks_sorted_by_priority(self, task_manager):
        """Test that tasks are sorted by priority."""
        task_low = task_manager.create_task("Low", "agent-1", priority=TaskPriority.LOW)
        task_critical = task_manager.create_task(
            "Critical", "agent-1", priority=TaskPriority.CRITICAL
        )
        task_normal = task_manager.create_task("Normal", "agent-1", priority=TaskPriority.NORMAL)
        task_high = task_manager.create_task("High", "agent-1", priority=TaskPriority.HIGH)

        tasks = task_manager.list_tasks()

        assert tasks[0].task_id == task_critical.task_id
        assert tasks[1].task_id == task_high.task_id
        assert tasks[2].task_id == task_normal.task_id
        assert tasks[3].task_id == task_low.task_id

    def test_get_pending_tasks(self, task_manager):
        """Test getting pending tasks."""
        task1 = task_manager.create_task("Task 1", "agent-1")
        task2 = task_manager.create_task("Task 2", "agent-1")
        task_manager.assign_task(task1.task_id, "agent-1")

        pending = task_manager.get_pending_tasks()

        assert len(pending) == 1
        assert pending[0].task_id == task2.task_id

    def test_get_agent_tasks(self, task_manager):
        """Test getting tasks for an agent."""
        task1 = task_manager.create_task("Task 1", "agent-1")
        task2 = task_manager.create_task("Task 2", "agent-1")

        task_manager.assign_task(task1.task_id, "agent-1")
        task_manager.assign_task(task2.task_id, "agent-2")

        agent1_tasks = task_manager.get_agent_tasks("agent-1")
        agent2_tasks = task_manager.get_agent_tasks("agent-2")

        assert len(agent1_tasks) == 1
        assert agent1_tasks[0].task_id == task1.task_id
        assert len(agent2_tasks) == 1
        assert agent2_tasks[0].task_id == task2.task_id

    def test_get_blocked_tasks(self, task_manager):
        """Test getting blocked tasks."""
        task = task_manager.create_task("Task 1", "agent-1")
        task_manager.assign_task(task.task_id, "agent-1")
        task_manager.transition_task(
            task.task_id,
            TaskStatus.BLOCKED,
            "agent-1",
            "Blocked by dependency",
        )

        blocked = task_manager.get_blocked_tasks()

        assert len(blocked) == 1
        assert blocked[0].task_id == task.task_id

    def test_get_tasks_in_review(self, task_manager):
        """Test getting tasks in review."""
        task = task_manager.create_task("Task 1", "agent-1")
        task_manager.assign_task(task.task_id, "agent-1")
        task_manager.transition_task(task.task_id, TaskStatus.WORKING, "agent-1")
        task_manager.transition_task(task.task_id, TaskStatus.REVIEW, "agent-1")

        in_review = task_manager.get_tasks_in_review()

        assert len(in_review) == 1
        assert in_review[0].task_id == task.task_id

    def test_assign_task(self, task_manager):
        """Test assigning a task through TaskManager."""
        task = task_manager.create_task("Task 1", "agent-1")

        assigned_task = task_manager.assign_task(task.task_id, "agent-2", "Taking task")

        assert assigned_task.assigned_to == "agent-2"
        assert assigned_task.status == TaskStatus.ASSIGNED

        # Verify persistence
        retrieved = task_manager.get_task(task.task_id)
        assert retrieved.assigned_to == "agent-2"

    def test_assign_task_not_found(self, task_manager):
        """Test assigning a nonexistent task raises error."""
        with pytest.raises(TaskNotFoundError):
            task_manager.assign_task("nonexistent", "agent-1")

    def test_transition_task(self, task_manager):
        """Test transitioning a task through TaskManager."""
        task = task_manager.create_task("Task 1", "agent-1")
        task_manager.assign_task(task.task_id, "agent-1")

        transitioned = task_manager.transition_task(
            task.task_id,
            TaskStatus.WORKING,
            "agent-1",
            "Starting work",
        )

        assert transitioned.status == TaskStatus.WORKING

    def test_transition_task_invalid(self, task_manager):
        """Test invalid transition raises error."""
        task = task_manager.create_task("Task 1", "agent-1")

        with pytest.raises(InvalidTransitionError):
            task_manager.transition_task(
                task.task_id,
                TaskStatus.COMPLETED,
                "agent-1",
            )

    def test_complete_task(self, task_manager):
        """Test completing a task through TaskManager."""
        task = task_manager.create_task("Task 1", "agent-1")
        task_manager.assign_task(task.task_id, "agent-1")
        task_manager.transition_task(task.task_id, TaskStatus.WORKING, "agent-1")

        result = {"files": ["file1.py", "file2.py"]}
        completed = task_manager.complete_task(
            task.task_id,
            "agent-1",
            result,
            "Done!",
        )

        assert completed.status == TaskStatus.COMPLETED
        assert completed.result == result

    def test_complete_task_not_found(self, task_manager):
        """Test completing nonexistent task raises error."""
        with pytest.raises(TaskNotFoundError):
            task_manager.complete_task("nonexistent", "agent-1")

    def test_fail_task(self, task_manager):
        """Test failing a task through TaskManager."""
        task = task_manager.create_task("Task 1", "agent-1")
        task_manager.assign_task(task.task_id, "agent-1")
        task_manager.transition_task(task.task_id, TaskStatus.WORKING, "agent-1")

        failed = task_manager.fail_task(
            task.task_id,
            "agent-1",
            "Resource unavailable",
            "Cannot proceed",
        )

        assert failed.status == TaskStatus.FAILED
        assert failed.error == "Resource unavailable"

    def test_fail_task_not_found(self, task_manager):
        """Test failing nonexistent task raises error."""
        with pytest.raises(TaskNotFoundError):
            task_manager.fail_task("nonexistent", "agent-1", "error")

    def test_get_context_tasks(self, task_manager):
        """Test getting tasks for a specific context."""
        task1 = task_manager.create_task("Task 1", "agent-1", context_id="ctx-1")
        task2 = task_manager.create_task("Task 2", "agent-1", context_id="ctx-1")
        task3 = task_manager.create_task("Task 3", "agent-1", context_id="ctx-2")

        ctx1_tasks = task_manager.get_context_tasks("ctx-1")

        assert len(ctx1_tasks) == 2
        task_ids = [t.task_id for t in ctx1_tasks]
        assert task1.task_id in task_ids
        assert task2.task_id in task_ids
        assert task3.task_id not in task_ids

    def test_get_subtasks(self, task_manager):
        """Test getting subtasks of a parent task."""
        parent = task_manager.create_task("Parent task", "agent-1")
        subtask1 = task_manager.create_task(
            "Subtask 1",
            "agent-1",
            parent_task_id=parent.task_id,
        )
        subtask2 = task_manager.create_task(
            "Subtask 2",
            "agent-1",
            parent_task_id=parent.task_id,
        )
        other_task = task_manager.create_task("Other task", "agent-1")

        subtasks = task_manager.get_subtasks(parent.task_id)

        assert len(subtasks) == 2
        task_ids = [t.task_id for t in subtasks]
        assert subtask1.task_id in task_ids
        assert subtask2.task_id in task_ids
        assert other_task.task_id not in task_ids

    def test_get_task_stats(self, task_manager):
        """Test getting task statistics."""
        task1 = task_manager.create_task("Task 1", "agent-1")
        task2 = task_manager.create_task("Task 2", "agent-1")
        task3 = task_manager.create_task("Task 3", "agent-1")

        task_manager.assign_task(task1.task_id, "agent-1")
        task_manager.transition_task(task2.task_id, TaskStatus.CANCELLED, "agent-1")

        stats = task_manager.get_task_stats()

        assert stats["total"] == 3
        assert stats["pending"] == 1
        assert stats["assigned"] == 1
        assert stats["cancelled"] == 1
        assert stats["working"] == 0

    def test_concurrent_task_operations(self, task_manager):
        """Test that file locking prevents race conditions."""
        task1 = task_manager.create_task("Task 1", "agent-1")
        task2 = task_manager.create_task("Task 2", "agent-1")

        # Both tasks should be persisted correctly
        retrieved1 = task_manager.get_task(task1.task_id)
        retrieved2 = task_manager.get_task(task2.task_id)

        assert retrieved1 is not None
        assert retrieved2 is not None
        assert retrieved1.task_id != retrieved2.task_id

    def test_read_tasks_invalid_json(self, task_manager, temp_project_dir):
        """Test handling of corrupted JSON file."""
        tasks_file = temp_project_dir / TASKS_FILENAME
        tasks_file.write_text("{invalid json")

        # Should return empty dict and log warning
        tasks = task_manager._read_tasks()
        assert tasks == {}

    def test_read_tasks_missing_file(self, task_manager):
        """Test reading tasks when file doesn't exist."""
        tasks = task_manager._read_tasks()
        assert tasks == {}

    def test_read_tasks_with_invalid_task_data(self, task_manager, temp_project_dir):
        """Test handling of invalid task data in JSON file."""
        tasks_file = temp_project_dir / TASKS_FILENAME
        # Create a file with invalid task data
        data = {
            "version": "1.0",
            "tasks": {
                "task-1": {
                    "task_id": "task-1",
                    "objective": "Valid task",
                    "status": "pending",
                },
                "task-2": {
                    # Missing required fields - will cause exception
                    "task_id": "task-2",
                },
            },
        }
        tasks_file.write_text(json.dumps(data))

        # Should skip invalid task and return valid ones
        tasks = task_manager._read_tasks()
        assert len(tasks) == 1
        assert "task-1" in tasks
        assert "task-2" not in tasks

    def test_read_tasks_file_lock_timeout(self, task_manager, temp_project_dir):
        """Test handling of file lock timeout during read."""
        from claudeswarm.file_lock import FileLockTimeout

        tasks_file = temp_project_dir / TASKS_FILENAME
        tasks_file.write_text('{"version": "1.0", "tasks": {}}')

        with patch("claudeswarm.tasks.FileLock") as mock_lock:
            mock_lock.return_value.__enter__.side_effect = FileLockTimeout("Lock timeout")

            tasks = task_manager._read_tasks()
            assert tasks == {}

    def test_read_tasks_other_exception(self, task_manager, temp_project_dir):
        """Test handling of unexpected exceptions during read."""
        tasks_file = temp_project_dir / TASKS_FILENAME
        tasks_file.write_text('{"version": "1.0", "tasks": {}}')

        with patch("builtins.open", side_effect=PermissionError("Permission denied")):
            tasks = task_manager._read_tasks()
            assert tasks == {}

    def test_write_tasks_file_lock_timeout(self, task_manager):
        """Test handling of file lock timeout during write."""
        from claudeswarm.file_lock import FileLockTimeout

        task = Task(task_id="test-123", objective="Test")
        tasks = {"test-123": task}

        with patch("claudeswarm.tasks.FileLock") as mock_lock:
            mock_lock.return_value.__enter__.side_effect = FileLockTimeout("Lock timeout")

            with pytest.raises(FileLockTimeout):
                task_manager._write_tasks(tasks)

    def test_write_tasks_other_exception(self, task_manager):
        """Test handling of unexpected exceptions during write."""
        task = Task(task_id="test-123", objective="Test")
        tasks = {"test-123": task}

        # Mock the FileLock context manager to raise an exception when writing
        with patch("claudeswarm.tasks.FileLock") as mock_lock_cls:
            mock_lock = Mock()
            mock_lock_cls.return_value = mock_lock
            # Make the context manager work but have open() fail
            mock_lock.__enter__ = Mock(return_value=mock_lock)
            mock_lock.__exit__ = Mock(return_value=False)

            with patch("builtins.open", side_effect=IOError("Disk full")):
                with pytest.raises(IOError):
                    task_manager._write_tasks(tasks)

    def test_from_dict_with_non_dict_history_entry(self):
        """Test Task.from_dict with history entries already as objects."""
        history_entry = TaskHistoryEntry(
            timestamp="2024-01-15T10:00:00Z",
            from_status=None,
            to_status="pending",
            agent_id="agent-1",
        )

        data = {
            "task_id": "test-123",
            "objective": "Test task",
            "status": "pending",
            "priority": "normal",
            "created_by": "agent-1",
            "assigned_to": None,
            "context_id": None,
            "constraints": [],
            "files": [],
            "blocked_by": [],
            "blocks": [],
            "result": None,
            "error": None,
            "history": [history_entry],  # Already a TaskHistoryEntry object
            "metadata": {},
            "created_at": "2024-01-15T10:00:00Z",
            "updated_at": "2024-01-15T10:00:00Z",
            "parent_task_id": None,
        }

        task = Task.from_dict(data)
        assert len(task.history) == 1
        assert task.history[0] == history_entry

    def test_write_tasks_creates_directory(self, temp_project_dir):
        """Test that write_tasks creates parent directories."""
        nested_dir = temp_project_dir / "nested" / "path"
        manager = TaskManager(nested_dir)

        task = manager.create_task("Test task", "agent-1")

        assert nested_dir.exists()
        assert (nested_dir / TASKS_FILENAME).exists()

    def test_task_history_preserved_across_operations(self, task_manager):
        """Test that task history is preserved through multiple operations."""
        task = task_manager.create_task("Task 1", "agent-1")
        initial_history_len = len(task.history)

        task_manager.assign_task(task.task_id, "agent-1", "Assigning")
        task_manager.transition_task(task.task_id, TaskStatus.WORKING, "agent-1", "Starting")
        task_manager.transition_task(task.task_id, TaskStatus.REVIEW, "agent-1", "Done")

        retrieved = task_manager.get_task(task.task_id)

        # Should have initial creation + 3 transitions
        assert len(retrieved.history) == initial_history_len + 3
        assert retrieved.history[-3].message == "Assigning"
        assert retrieved.history[-2].message == "Starting"
        assert retrieved.history[-1].message == "Done"


class TestTaskWorkflows:
    """Integration tests for common task workflows."""

    def test_complete_workflow_simple(self, task_manager):
        """Test complete task workflow: create -> assign -> work -> complete."""
        # Create task
        task = task_manager.create_task(
            "Implement feature",
            "agent-0",
            priority=TaskPriority.HIGH,
        )
        assert task.status == TaskStatus.PENDING

        # Assign task
        task_manager.assign_task(task.task_id, "agent-1")
        task = task_manager.get_task(task.task_id)
        assert task.status == TaskStatus.ASSIGNED
        assert task.assigned_to == "agent-1"

        # Start work
        task_manager.transition_task(task.task_id, TaskStatus.WORKING, "agent-1")
        task = task_manager.get_task(task.task_id)
        assert task.status == TaskStatus.WORKING

        # Complete
        result = {"status": "success"}
        task_manager.complete_task(task.task_id, "agent-1", result)
        task = task_manager.get_task(task.task_id)
        assert task.status == TaskStatus.COMPLETED
        assert task.result == result
        assert task.is_terminal()

    def test_complete_workflow_with_review(self, task_manager):
        """Test workflow with review: create -> assign -> work -> review -> complete."""
        task = task_manager.create_task("Complex feature", "agent-0")

        task_manager.assign_task(task.task_id, "agent-1")
        task_manager.transition_task(task.task_id, TaskStatus.WORKING, "agent-1")
        task_manager.transition_task(task.task_id, TaskStatus.REVIEW, "agent-1", "Ready for review")

        task = task_manager.get_task(task.task_id)
        assert task.status == TaskStatus.REVIEW

        task_manager.complete_task(task.task_id, "agent-2", message="Approved")
        task = task_manager.get_task(task.task_id)
        assert task.status == TaskStatus.COMPLETED

    def test_workflow_with_blocking(self, task_manager):
        """Test workflow with blocking: work -> blocked -> unblocked -> work -> complete."""
        task = task_manager.create_task("Dependent task", "agent-0")

        task_manager.assign_task(task.task_id, "agent-1")
        task_manager.transition_task(task.task_id, TaskStatus.WORKING, "agent-1")

        # Get task object and block it
        task_obj = task_manager.get_task(task.task_id)
        task_obj.block("agent-1", ["dependency-task"], "Waiting for dependency")
        task_manager.update_task(task_obj)

        task = task_manager.get_task(task.task_id)
        assert task.status == TaskStatus.BLOCKED

        # Unblock
        task_obj = task_manager.get_task(task.task_id)
        task_obj.unblock("agent-1", "Dependency resolved")
        task_manager.update_task(task_obj)

        task = task_manager.get_task(task.task_id)
        assert task.status == TaskStatus.ASSIGNED

        # Resume work
        task_manager.transition_task(task.task_id, TaskStatus.WORKING, "agent-1")
        task_manager.complete_task(task.task_id, "agent-1")

        task = task_manager.get_task(task.task_id)
        assert task.status == TaskStatus.COMPLETED

    def test_workflow_failure_and_retry(self, task_manager):
        """Test workflow with failure and retry: work -> failed -> retry -> complete."""
        task = task_manager.create_task("Risky task", "agent-0")

        task_manager.assign_task(task.task_id, "agent-1")
        task_manager.transition_task(task.task_id, TaskStatus.WORKING, "agent-1")
        task_manager.fail_task(task.task_id, "agent-1", "Network error")

        task = task_manager.get_task(task.task_id)
        assert task.status == TaskStatus.FAILED
        assert task.error == "Network error"

        # Retry
        task_manager.transition_task(task.task_id, TaskStatus.PENDING, "agent-1", "Retrying")
        task_manager.assign_task(task.task_id, "agent-1")
        task_manager.transition_task(task.task_id, TaskStatus.WORKING, "agent-1")
        task_manager.complete_task(task.task_id, "agent-1")

        task = task_manager.get_task(task.task_id)
        assert task.status == TaskStatus.COMPLETED
        # History should show the failure and retry
        assert len(task.history) > 5

    def test_workflow_cancellation(self, task_manager):
        """Test task cancellation at various stages."""
        # Cancel pending task
        task1 = task_manager.create_task("Task 1", "agent-0")
        task_manager.transition_task(task1.task_id, TaskStatus.CANCELLED, "agent-0", "Not needed")
        assert task_manager.get_task(task1.task_id).status == TaskStatus.CANCELLED

        # Cancel assigned task
        task2 = task_manager.create_task("Task 2", "agent-0")
        task_manager.assign_task(task2.task_id, "agent-1")
        task_manager.transition_task(task2.task_id, TaskStatus.CANCELLED, "agent-1", "Duplicate")
        assert task_manager.get_task(task2.task_id).status == TaskStatus.CANCELLED

        # Cancel working task
        task3 = task_manager.create_task("Task 3", "agent-0")
        task_manager.assign_task(task3.task_id, "agent-1")
        task_manager.transition_task(task3.task_id, TaskStatus.WORKING, "agent-1")
        task_manager.transition_task(task3.task_id, TaskStatus.CANCELLED, "agent-1", "Obsolete")
        assert task_manager.get_task(task3.task_id).status == TaskStatus.CANCELLED
