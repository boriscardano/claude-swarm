"""Unit tests for context.py module.

Tests cover:
- SharedContext creation and operations
- Decision tracking
- File tracking with path validation
- ContextStore CRUD operations
- Context linking and search
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, mock_open, patch

import pytest

from claudeswarm.context import (
    CONTEXTS_FILENAME,
    MAX_DECISIONS_PER_CONTEXT,
    MAX_FILES_PER_CONTEXT,
    ContextDecision,
    ContextStore,
    SharedContext,
    get_contexts_path,
)


class TestContextDecision:
    """Tests for ContextDecision dataclass."""

    def test_creation_with_defaults(self):
        """Test ContextDecision creation with default values."""
        decision = ContextDecision(
            decision="Use REST API",
            by="agent-0",
            reason="Better compatibility",
        )

        assert decision.decision == "Use REST API"
        assert decision.by == "agent-0"
        assert decision.reason == "Better compatibility"
        assert isinstance(decision.timestamp, str)
        assert decision.alternatives_considered == []
        assert decision.metadata == {}

    def test_creation_with_alternatives(self):
        """Test ContextDecision with alternatives considered."""
        decision = ContextDecision(
            decision="Use REST API",
            by="agent-0",
            reason="Better compatibility",
            alternatives_considered=["GraphQL", "gRPC"],
        )

        assert decision.alternatives_considered == ["GraphQL", "gRPC"]

    def test_to_dict(self):
        """Test conversion to dictionary."""
        decision = ContextDecision(
            decision="Use REST API",
            by="agent-0",
            reason="Better compatibility",
            metadata={"confidence": 0.9},
        )

        result = decision.to_dict()

        assert result["decision"] == "Use REST API"
        assert result["by"] == "agent-0"
        assert result["reason"] == "Better compatibility"
        assert result["metadata"] == {"confidence": 0.9}
        assert "timestamp" in result

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "decision": "Use REST API",
            "by": "agent-0",
            "reason": "Better compatibility",
            "timestamp": "2024-01-01T00:00:00Z",
            "alternatives_considered": ["GraphQL"],
            "metadata": {"confidence": 0.9},
        }

        decision = ContextDecision.from_dict(data)

        assert decision.decision == "Use REST API"
        assert decision.by == "agent-0"
        assert decision.timestamp == "2024-01-01T00:00:00Z"
        assert decision.alternatives_considered == ["GraphQL"]


class TestSharedContext:
    """Tests for SharedContext dataclass."""

    def test_creation_minimal(self):
        """Test SharedContext creation with minimal parameters."""
        ctx = SharedContext(
            context_id="test-ctx",
            name="Test Context",
        )

        assert ctx.context_id == "test-ctx"
        assert ctx.name == "Test Context"
        assert ctx.summary == ""
        assert ctx.status == "active"
        assert ctx.decisions == []
        assert ctx.files_touched == []
        assert ctx.related_contexts == []
        assert ctx.agents_involved == []

    def test_creation_full(self):
        """Test SharedContext creation with all parameters."""
        ctx = SharedContext(
            context_id="test-ctx",
            name="Test Context",
            summary="Testing context",
            status="active",
            created_by="agent-0",
            agents_involved=["agent-0"],
        )

        assert ctx.context_id == "test-ctx"
        assert ctx.created_by == "agent-0"
        assert ctx.agents_involved == ["agent-0"]

    def test_add_decision(self):
        """Test adding a decision to context."""
        ctx = SharedContext(context_id="test-ctx", name="Test Context")

        decision = ctx.add_decision(
            decision="Use PostgreSQL",
            by="agent-1",
            reason="Better for relational data",
            alternatives=["MongoDB", "MySQL"],
        )

        assert len(ctx.decisions) == 1
        assert decision.decision == "Use PostgreSQL"
        assert decision.by == "agent-1"
        assert decision.alternatives_considered == ["MongoDB", "MySQL"]
        assert "agent-1" in ctx.agents_involved

    def test_add_decision_trim_when_exceeds_max(self):
        """Test that decisions are trimmed when exceeding MAX_DECISIONS_PER_CONTEXT."""
        ctx = SharedContext(context_id="test-ctx", name="Test Context")

        # Add MAX_DECISIONS_PER_CONTEXT + 1 decisions
        for i in range(MAX_DECISIONS_PER_CONTEXT + 1):
            ctx.add_decision(
                decision=f"Decision {i}",
                by="agent-0",
            )

        # Should keep only MAX_DECISIONS_PER_CONTEXT decisions
        assert len(ctx.decisions) == MAX_DECISIONS_PER_CONTEXT
        # Most recent should be kept
        assert ctx.decisions[-1].decision == f"Decision {MAX_DECISIONS_PER_CONTEXT}"

    def test_add_file_valid_relative_path(self):
        """Test adding a valid relative file path."""
        ctx = SharedContext(context_id="test-ctx", name="Test Context")

        ctx.add_file("src/auth.py", agent_id="agent-0")

        assert "src/auth.py" in ctx.files_touched
        assert "agent-0" in ctx.agents_involved

    def test_add_file_rejects_absolute_path(self):
        """Test that absolute paths are rejected."""
        ctx = SharedContext(context_id="test-ctx", name="Test Context")

        with pytest.raises(ValueError, match="Absolute paths not allowed"):
            ctx.add_file("/etc/passwd")

    def test_add_file_rejects_path_traversal(self):
        """Test that path traversal attempts are rejected."""
        ctx = SharedContext(context_id="test-ctx", name="Test Context")

        with pytest.raises(ValueError, match="Path traversal not allowed"):
            ctx.add_file("../../../etc/passwd")

        with pytest.raises(ValueError, match="Path traversal not allowed"):
            ctx.add_file("src/../../etc/passwd")

    def test_add_file_no_duplicates(self):
        """Test that duplicate files are not added."""
        ctx = SharedContext(context_id="test-ctx", name="Test Context")

        ctx.add_file("src/auth.py")
        ctx.add_file("src/auth.py")

        assert ctx.files_touched.count("src/auth.py") == 1

    def test_add_file_trim_when_exceeds_max(self):
        """Test that files are trimmed when exceeding MAX_FILES_PER_CONTEXT."""
        ctx = SharedContext(context_id="test-ctx", name="Test Context")

        # Add MAX_FILES_PER_CONTEXT + 1 files
        for i in range(MAX_FILES_PER_CONTEXT + 1):
            ctx.add_file(f"file{i}.py")

        # Should keep only MAX_FILES_PER_CONTEXT files
        assert len(ctx.files_touched) == MAX_FILES_PER_CONTEXT
        # Most recent should be kept
        assert f"file{MAX_FILES_PER_CONTEXT}.py" in ctx.files_touched

    def test_add_related_context(self):
        """Test adding a related context."""
        ctx = SharedContext(context_id="test-ctx", name="Test Context")

        ctx.add_related_context("other-ctx")

        assert "other-ctx" in ctx.related_contexts

    def test_add_related_context_no_self_reference(self):
        """Test that context cannot reference itself."""
        ctx = SharedContext(context_id="test-ctx", name="Test Context")

        ctx.add_related_context("test-ctx")

        assert "test-ctx" not in ctx.related_contexts

    def test_add_related_context_no_duplicates(self):
        """Test that duplicate related contexts are not added."""
        ctx = SharedContext(context_id="test-ctx", name="Test Context")

        ctx.add_related_context("other-ctx")
        ctx.add_related_context("other-ctx")

        assert ctx.related_contexts.count("other-ctx") == 1

    def test_add_task(self):
        """Test adding a task to context."""
        ctx = SharedContext(context_id="test-ctx", name="Test Context")

        ctx.add_task("task-123")

        assert "task-123" in ctx.tasks

    def test_add_message(self):
        """Test adding a message to context."""
        ctx = SharedContext(context_id="test-ctx", name="Test Context")

        ctx.add_message("msg-123")

        assert "msg-123" in ctx.messages

    def test_complete(self):
        """Test completing a context."""
        ctx = SharedContext(context_id="test-ctx", name="Test Context")

        ctx.complete(by="agent-0", summary="All tasks completed")

        assert ctx.status == "completed"
        assert ctx.summary == "All tasks completed"
        assert "agent-0" in ctx.agents_involved

    def test_archive(self):
        """Test archiving a context."""
        ctx = SharedContext(context_id="test-ctx", name="Test Context")

        ctx.archive()

        assert ctx.status == "archived"

    def test_to_dict(self):
        """Test conversion to dictionary."""
        ctx = SharedContext(
            context_id="test-ctx",
            name="Test Context",
            summary="Testing",
            created_by="agent-0",
        )
        ctx.add_decision("Use Python", "agent-0")

        result = ctx.to_dict()

        assert result["context_id"] == "test-ctx"
        assert result["name"] == "Test Context"
        assert result["summary"] == "Testing"
        assert len(result["decisions"]) == 1
        assert isinstance(result["decisions"][0], dict)

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "context_id": "test-ctx",
            "name": "Test Context",
            "summary": "Testing",
            "status": "active",
            "decisions": [
                {
                    "decision": "Use Python",
                    "by": "agent-0",
                    "reason": "Better libraries",
                    "timestamp": "2024-01-01T00:00:00Z",
                    "alternatives_considered": [],
                    "metadata": {},
                }
            ],
            "files_touched": ["src/main.py"],
            "related_contexts": ["other-ctx"],
            "agents_involved": ["agent-0"],
            "tasks": ["task-1"],
            "messages": ["msg-1"],
            "created_by": "agent-0",
        }

        ctx = SharedContext.from_dict(data)

        assert ctx.context_id == "test-ctx"
        assert ctx.name == "Test Context"
        assert len(ctx.decisions) == 1
        assert isinstance(ctx.decisions[0], ContextDecision)
        assert ctx.files_touched == ["src/main.py"]
        assert ctx.related_contexts == ["other-ctx"]


class TestGetContextsPath:
    """Tests for get_contexts_path function."""

    @patch("claudeswarm.context.get_project_root")
    def test_get_contexts_path_default(self, mock_get_root):
        """Test getting contexts path with default project root."""
        mock_get_root.return_value = Path("/project")

        result = get_contexts_path()

        assert result == Path("/project") / CONTEXTS_FILENAME
        mock_get_root.assert_called_once_with(None)

    @patch("claudeswarm.context.get_project_root")
    def test_get_contexts_path_custom_root(self, mock_get_root):
        """Test getting contexts path with custom project root."""
        custom_root = Path("/custom")
        mock_get_root.return_value = custom_root

        result = get_contexts_path(custom_root)

        assert result == custom_root / CONTEXTS_FILENAME
        mock_get_root.assert_called_once_with(custom_root)


class TestContextStore:
    """Tests for ContextStore class."""

    @pytest.fixture
    def temp_project(self, tmp_path):
        """Create a temporary project directory."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        return project_root

    @pytest.fixture
    def store(self, temp_project):
        """Create a ContextStore instance."""
        return ContextStore(temp_project)

    def test_initialization(self, temp_project):
        """Test ContextStore initialization."""
        store = ContextStore(temp_project)

        assert store.project_root == temp_project
        assert store.contexts_path == temp_project / CONTEXTS_FILENAME

    def test_create_context_minimal(self, store):
        """Test creating a context with minimal parameters."""
        ctx = store.create_context(
            name="Test Context",
            created_by="agent-0",
        )

        assert ctx.name == "Test Context"
        assert ctx.created_by == "agent-0"
        assert "agent-0" in ctx.agents_involved
        assert ctx.context_id is not None

    def test_create_context_with_custom_id(self, store):
        """Test creating a context with custom ID."""
        ctx = store.create_context(
            name="Test Context",
            created_by="agent-0",
            context_id="custom-id",
        )

        assert ctx.context_id == "custom-id"

    def test_create_context_with_related(self, store):
        """Test creating a context with related contexts."""
        ctx = store.create_context(
            name="Test Context",
            created_by="agent-0",
            related_contexts=["other-ctx"],
        )

        assert "other-ctx" in ctx.related_contexts

    def test_create_context_persists_to_file(self, store):
        """Test that creating a context persists to file."""
        ctx = store.create_context(
            name="Test Context",
            created_by="agent-0",
            context_id="test-ctx",
        )

        # Verify file was created
        assert store.contexts_path.exists()

        # Read file and verify content
        with open(store.contexts_path) as f:
            data = json.load(f)

        assert "test-ctx" in data["contexts"]
        assert data["contexts"]["test-ctx"]["name"] == "Test Context"

    def test_get_context_existing(self, store):
        """Test getting an existing context."""
        # Create a context
        created = store.create_context(
            name="Test Context",
            created_by="agent-0",
            context_id="test-ctx",
        )

        # Get the context
        retrieved = store.get_context("test-ctx")

        assert retrieved is not None
        assert retrieved.context_id == created.context_id
        assert retrieved.name == created.name

    def test_get_context_nonexistent(self, store):
        """Test getting a nonexistent context."""
        result = store.get_context("nonexistent")

        assert result is None

    def test_update_context(self, store):
        """Test updating a context."""
        # Create a context
        ctx = store.create_context(
            name="Test Context",
            created_by="agent-0",
            context_id="test-ctx",
        )

        # Update the context
        ctx.summary = "Updated summary"
        ctx.add_file("src/new.py")
        store.update_context(ctx)

        # Retrieve and verify
        updated = store.get_context("test-ctx")
        assert updated.summary == "Updated summary"
        assert "src/new.py" in updated.files_touched

    def test_delete_context_existing(self, store):
        """Test deleting an existing context."""
        # Create a context
        store.create_context(
            name="Test Context",
            created_by="agent-0",
            context_id="test-ctx",
        )

        # Delete it
        result = store.delete_context("test-ctx")

        assert result is True
        assert store.get_context("test-ctx") is None

    def test_delete_context_nonexistent(self, store):
        """Test deleting a nonexistent context."""
        result = store.delete_context("nonexistent")

        assert result is False

    def test_list_contexts_empty(self, store):
        """Test listing contexts when none exist."""
        result = store.list_contexts()

        assert result == []

    def test_list_contexts_all(self, store):
        """Test listing all contexts."""
        # Create multiple contexts
        store.create_context("Context 1", "agent-0", context_id="ctx-1")
        store.create_context("Context 2", "agent-0", context_id="ctx-2")
        store.create_context("Context 3", "agent-0", context_id="ctx-3")

        result = store.list_contexts()

        assert len(result) == 3
        # Should be sorted by updated_at, most recent first
        assert all(isinstance(ctx, SharedContext) for ctx in result)

    def test_list_contexts_filter_by_status(self, store):
        """Test listing contexts filtered by status."""
        # Create contexts with different statuses
        ctx1 = store.create_context("Context 1", "agent-0", context_id="ctx-1")
        store.create_context("Context 2", "agent-0", context_id="ctx-2")

        # Complete one
        store.complete_context("ctx-1", "agent-0")

        # List only active
        result = store.list_contexts(status="active")
        assert len(result) == 1
        assert result[0].context_id == "ctx-2"

        # List only completed
        result = store.list_contexts(status="completed")
        assert len(result) == 1
        assert result[0].context_id == "ctx-1"

    def test_list_contexts_filter_by_agent(self, store):
        """Test listing contexts filtered by agent."""
        # Create contexts with different agents
        store.create_context("Context 1", "agent-0", context_id="ctx-1")
        store.create_context("Context 2", "agent-1", context_id="ctx-2")

        # List contexts for agent-0
        result = store.list_contexts(agent_id="agent-0")
        assert len(result) == 1
        assert result[0].created_by == "agent-0"

    def test_list_contexts_exclude_archived(self, store):
        """Test that archived contexts are excluded by default."""
        # Create and archive a context
        store.create_context("Context 1", "agent-0", context_id="ctx-1")
        store.archive_context("ctx-1")

        # List without archived
        result = store.list_contexts()
        assert len(result) == 0

        # List with archived
        result = store.list_contexts(include_archived=True)
        assert len(result) == 1

    def test_get_active_contexts(self, store):
        """Test getting only active contexts."""
        # Create contexts with different statuses
        store.create_context("Context 1", "agent-0", context_id="ctx-1")
        store.create_context("Context 2", "agent-0", context_id="ctx-2")
        store.complete_context("ctx-2", "agent-0")

        result = store.get_active_contexts()

        assert len(result) == 1
        assert result[0].status == "active"

    def test_add_decision(self, store):
        """Test adding a decision to a context."""
        # Create a context
        store.create_context("Context 1", "agent-0", context_id="ctx-1")

        # Add decision
        decision = store.add_decision(
            "ctx-1",
            decision="Use Redis",
            by="agent-1",
            reason="Fast caching",
        )

        assert decision is not None
        assert decision.decision == "Use Redis"

        # Verify persistence
        ctx = store.get_context("ctx-1")
        assert len(ctx.decisions) == 1

    def test_add_decision_nonexistent_context(self, store):
        """Test adding decision to nonexistent context."""
        result = store.add_decision(
            "nonexistent",
            decision="Use Redis",
            by="agent-0",
        )

        assert result is None

    def test_touch_file(self, store):
        """Test recording a file touch."""
        # Create a context
        store.create_context("Context 1", "agent-0", context_id="ctx-1")

        # Touch a file
        result = store.touch_file("ctx-1", "src/main.py", "agent-1")

        assert result is True

        # Verify persistence
        ctx = store.get_context("ctx-1")
        assert "src/main.py" in ctx.files_touched
        assert "agent-1" in ctx.agents_involved

    def test_touch_file_nonexistent_context(self, store):
        """Test touching file in nonexistent context."""
        result = store.touch_file("nonexistent", "src/main.py")

        assert result is False

    def test_link_contexts(self, store):
        """Test linking two contexts."""
        # Create two contexts
        store.create_context("Context 1", "agent-0", context_id="ctx-1")
        store.create_context("Context 2", "agent-0", context_id="ctx-2")

        # Link them
        result = store.link_contexts("ctx-1", "ctx-2")

        assert result is True

        # Verify bidirectional link
        ctx1 = store.get_context("ctx-1")
        ctx2 = store.get_context("ctx-2")
        assert "ctx-2" in ctx1.related_contexts
        assert "ctx-1" in ctx2.related_contexts

    def test_link_contexts_nonexistent(self, store):
        """Test linking with nonexistent context."""
        store.create_context("Context 1", "agent-0", context_id="ctx-1")

        result = store.link_contexts("ctx-1", "nonexistent")

        assert result is False

    def test_get_or_create_context_existing(self, store):
        """Test get_or_create with existing context."""
        # Create a context
        original = store.create_context("Context 1", "agent-0", context_id="ctx-1")

        # Get or create should return existing
        result = store.get_or_create_context(
            "ctx-1",
            name="Different Name",
            created_by="agent-1",
        )

        assert result.context_id == original.context_id
        assert result.name == original.name  # Should keep original name

    def test_get_or_create_context_new(self, store):
        """Test get_or_create with new context."""
        result = store.get_or_create_context(
            "new-ctx",
            name="New Context",
            created_by="agent-0",
        )

        assert result.context_id == "new-ctx"
        assert result.name == "New Context"

    def test_complete_context(self, store):
        """Test completing a context."""
        store.create_context("Context 1", "agent-0", context_id="ctx-1")

        result = store.complete_context("ctx-1", "agent-1", "All done")

        assert result is True

        ctx = store.get_context("ctx-1")
        assert ctx.status == "completed"
        assert ctx.summary == "All done"
        assert "agent-1" in ctx.agents_involved

    def test_archive_context(self, store):
        """Test archiving a context."""
        store.create_context("Context 1", "agent-0", context_id="ctx-1")

        result = store.archive_context("ctx-1")

        assert result is True

        ctx = store.get_context("ctx-1")
        assert ctx.status == "archived"

    def test_search_contexts_by_name(self, store):
        """Test searching contexts by name."""
        store.create_context("Auth Feature", "agent-0", context_id="ctx-1")
        store.create_context("Database Migration", "agent-0", context_id="ctx-2")
        store.create_context("API Enhancement", "agent-0", context_id="ctx-3")

        # Search for "auth"
        result = store.search_contexts("auth")

        assert len(result) == 1
        assert result[0].name == "Auth Feature"

    def test_search_contexts_by_summary(self, store):
        """Test searching contexts by summary."""
        store.create_context("Feature 1", "agent-0", summary="JWT authentication", context_id="ctx-1")
        store.create_context("Feature 2", "agent-0", summary="Database setup", context_id="ctx-2")

        result = store.search_contexts("JWT")

        assert len(result) == 1
        assert result[0].context_id == "ctx-1"

    def test_search_contexts_case_insensitive(self, store):
        """Test that search is case insensitive."""
        store.create_context("Auth Feature", "agent-0", context_id="ctx-1")

        result = store.search_contexts("AUTH")

        assert len(result) == 1

    def test_get_context_summary(self, store):
        """Test getting a context summary."""
        ctx = store.create_context("Test Context", "agent-0", context_id="ctx-1")
        ctx.add_decision("Use Redis", "agent-0")
        ctx.add_file("src/main.py")
        store.update_context(ctx)

        summary = store.get_context_summary("ctx-1")

        assert summary is not None
        assert summary["context_id"] == "ctx-1"
        assert summary["name"] == "Test Context"
        assert summary["agents_count"] == 1
        assert summary["decisions_count"] == 1
        assert summary["files_count"] == 1
        assert "created_at" in summary
        assert "updated_at" in summary

    def test_get_context_summary_nonexistent(self, store):
        """Test getting summary for nonexistent context."""
        result = store.get_context_summary("nonexistent")

        assert result is None

    @patch("claudeswarm.context.FileLock")
    def test_read_contexts_handles_lock_timeout(self, mock_filelock, store):
        """Test that read_contexts handles lock timeout gracefully."""
        from claudeswarm.file_lock import FileLockTimeout

        # Create contexts file
        store.create_context("Test", "agent-0")

        # Make FileLock raise timeout
        mock_filelock.side_effect = FileLockTimeout("Timeout")

        # Should return empty dict on timeout
        result = store._read_contexts()
        assert result == {}

    def test_read_contexts_handles_missing_file(self, store):
        """Test that read_contexts handles missing file gracefully."""
        result = store._read_contexts()

        assert result == {}
        assert not store.contexts_path.exists()
