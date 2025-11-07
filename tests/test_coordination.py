"""Unit tests for coordination file management.

Tests cover:
- Template generation
- File initialization
- Section parsing
- Section updates with locking
- Atomic writes
- Concurrent updates
- Query functions
- Helper functions for adding items
"""

import tempfile
import threading
import time
from pathlib import Path

import pytest

from claudeswarm.coordination import (
    COORDINATION_FILENAME,
    CoordinationFile,
    CoordinationSection,
    _reset_default_coordination,
    add_blocked_item,
    add_current_work,
    add_decision,
    add_review_item,
    get_blocked_items,
    get_current_work,
    get_decisions,
    get_review_queue,
    get_section,
    init_coordination_file,
    update_section,
)
from claudeswarm.locking import LockManager


@pytest.fixture(autouse=True)
def reset_coordination():
    """Reset module-level coordination state before each test."""
    _reset_default_coordination()
    yield
    _reset_default_coordination()


@pytest.fixture
def temp_project():
    """Create a temporary project directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def coord_file(temp_project):
    """Create a CoordinationFile instance with a temporary directory."""
    return CoordinationFile(project_root=temp_project, agent_id="test-agent")


@pytest.fixture
def initialized_coord(coord_file):
    """Create and initialize a coordination file."""
    coord_file.init_file(project_name="Test Project")
    return coord_file


class TestCoordinationFileInit:
    """Tests for coordination file initialization."""

    def test_template_generation(self):
        """Test that template is generated correctly."""
        template = CoordinationFile.get_template("Test Project")

        assert "# Coordination File - Test Project" in template
        assert "## Sprint Goals" in template
        assert "## Current Work" in template
        assert "## Blocked Items" in template
        assert "## Code Review Queue" in template
        assert "## Decisions" in template

    def test_init_creates_file(self, coord_file):
        """Test that init_file creates the coordination file."""
        result = coord_file.init_file(project_name="Test Project")

        assert result is True
        assert coord_file.filepath.exists()
        content = coord_file.filepath.read_text()
        assert "# Coordination File - Test Project" in content

    def test_init_fails_if_exists(self, initialized_coord):
        """Test that init_file raises error if file exists."""
        with pytest.raises(FileExistsError):
            initialized_coord.init_file()

    def test_init_with_force_overwrites(self, initialized_coord):
        """Test that force=True overwrites existing file."""
        # Modify the file
        initialized_coord.filepath.write_text("Modified content")

        # Re-initialize with force
        result = initialized_coord.init_file(project_name="New Project", force=True)

        assert result is True
        content = initialized_coord.filepath.read_text()
        assert "# Coordination File - New Project" in content
        assert "Modified content" not in content


class TestSectionParsing:
    """Tests for section parsing functionality."""

    def test_parse_all_sections(self, initialized_coord):
        """Test parsing all sections from template."""
        content = initialized_coord.read_file()
        sections = initialized_coord._parse_sections(content)

        expected_sections = [
            "Sprint Goals",
            "Current Work",
            "Blocked Items",
            "Code Review Queue",
            "Decisions",
        ]
        for section_name in expected_sections:
            assert section_name in sections
            assert isinstance(sections[section_name], CoordinationSection)

    def test_section_content_extraction(self, initialized_coord):
        """Test that section content is extracted correctly."""
        content = initialized_coord.read_file()
        sections = initialized_coord._parse_sections(content)

        current_work = sections["Current Work"]
        assert "| Agent | Task | Status | Started |" in current_work.content
        assert "example-agent" in current_work.content

    def test_get_section(self, initialized_coord):
        """Test getting a specific section."""
        section_content = initialized_coord.get_section("Sprint Goals")

        assert section_content is not None
        assert "Add sprint goals here" in section_content

    def test_get_nonexistent_section(self, initialized_coord):
        """Test getting a section that doesn't exist."""
        section_content = initialized_coord.get_section("Nonexistent Section")
        assert section_content is None


class TestSectionUpdates:
    """Tests for section update functionality."""

    def test_update_existing_section(self, initialized_coord):
        """Test updating an existing section."""
        new_content = "- Updated sprint goal 1\n- Updated sprint goal 2"
        result = initialized_coord.update_section("Sprint Goals", new_content)

        assert result is True

        # Verify update
        updated_content = initialized_coord.get_section("Sprint Goals")
        assert updated_content == new_content

    def test_update_preserves_other_sections(self, initialized_coord):
        """Test that updating one section doesn't affect others."""
        # Get original content of another section
        original_current_work = initialized_coord.get_section("Current Work")

        # Update different section
        new_goals = "- New goal"
        initialized_coord.update_section("Sprint Goals", new_goals)

        # Verify other section unchanged
        current_work = initialized_coord.get_section("Current Work")
        assert current_work == original_current_work

    def test_update_creates_new_section(self, initialized_coord):
        """Test that updating a non-existent section creates it."""
        new_section = "New Section"
        content = "This is a new section"

        result = initialized_coord.update_section(new_section, content)

        assert result is True
        retrieved_content = initialized_coord.get_section(new_section)
        assert retrieved_content == content

    def test_append_to_section(self, initialized_coord):
        """Test appending content to a section."""
        original = initialized_coord.get_section("Sprint Goals")

        new_line = "- Appended goal"
        initialized_coord.append_to_section("Sprint Goals", new_line)

        updated = initialized_coord.get_section("Sprint Goals")
        assert original in updated
        assert new_line in updated


class TestLockIntegration:
    """Tests for lock integration in coordination file updates."""

    def test_update_acquires_and_releases_lock(self, initialized_coord):
        """Test that updates acquire and release locks properly."""
        # Update should succeed
        result = initialized_coord.update_section("Sprint Goals", "- Test goal")
        assert result is True

        # Lock should be released - verify by checking lock doesn't exist
        lock = initialized_coord.lock_manager.who_has_lock(str(initialized_coord.filepath))
        assert lock is None

    def test_concurrent_update_blocks(self, initialized_coord):
        """Test that concurrent updates are blocked by locks."""
        # Create second coordination instance for same file
        coord2 = CoordinationFile(
            project_root=initialized_coord.project_root,
            agent_id="agent-2",
            lock_manager=initialized_coord.lock_manager,
        )

        # Acquire lock manually
        success, _ = initialized_coord.lock_manager.acquire_lock(
            str(initialized_coord.filepath), initialized_coord.agent_id, "testing"
        )
        assert success is True

        try:
            # Second agent should fail to update
            with pytest.raises(RuntimeError, match="Cannot acquire lock"):
                coord2.update_section("Sprint Goals", "Should fail")
        finally:
            # Clean up lock
            initialized_coord.lock_manager.release_lock(
                str(initialized_coord.filepath), initialized_coord.agent_id
            )

    def test_same_agent_can_reacquire_lock(self, initialized_coord):
        """Test that same agent can update multiple times."""
        # First update
        result1 = initialized_coord.update_section("Sprint Goals", "- Goal 1")
        assert result1 is True

        # Second update by same agent
        result2 = initialized_coord.update_section("Sprint Goals", "- Goal 2")
        assert result2 is True


class TestAtomicUpdates:
    """Tests for atomic file updates."""

    def test_update_is_atomic(self, initialized_coord):
        """Test that updates are atomic (file is never in invalid state)."""
        # This test verifies that temp file + rename pattern is used
        original_content = initialized_coord.read_file()

        # Update
        initialized_coord.update_section("Sprint Goals", "- New goal")

        # File should exist and be valid
        assert initialized_coord.filepath.exists()
        new_content = initialized_coord.read_file()
        assert "- New goal" in new_content

        # No .tmp files should remain
        tmp_files = list(initialized_coord.project_root.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_concurrent_updates_to_different_sections(self, temp_project):
        """Test concurrent updates to different sections work correctly."""
        # Initialize file
        coord1 = CoordinationFile(project_root=temp_project, agent_id="agent-1")
        coord1.init_file()

        coord2 = CoordinationFile(
            project_root=temp_project,
            agent_id="agent-2",
            lock_manager=coord1.lock_manager,
        )

        results = {"agent1": None, "agent2": None}
        errors = {"agent1": None, "agent2": None}

        def update_goals():
            try:
                # Small delay to ensure both try to update around same time
                time.sleep(0.01)
                results["agent1"] = coord1.update_section(
                    "Sprint Goals", "- Goal from agent 1"
                )
            except Exception as e:
                errors["agent1"] = e

        def update_decisions():
            try:
                time.sleep(0.01)
                results["agent2"] = coord2.update_section(
                    "Decisions", "- **[2025-11-07]** Decision from agent 2: test"
                )
            except Exception as e:
                errors["agent2"] = e

        # Run concurrent updates
        t1 = threading.Thread(target=update_goals)
        t2 = threading.Thread(target=update_decisions)

        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        # At least one should succeed (both might succeed depending on timing)
        # The key is that neither should corrupt the file
        assert errors["agent1"] is None or isinstance(errors["agent1"], RuntimeError)
        assert errors["agent2"] is None or isinstance(errors["agent2"], RuntimeError)

        # File should still be valid and parseable
        content = coord1.read_file()
        sections = coord1._parse_sections(content)
        assert len(sections) >= 2  # At least some sections should exist


class TestQueryFunctions:
    """Tests for query functions."""

    def test_get_current_work_empty(self, initialized_coord):
        """Test getting current work from initialized file."""
        work_items = initialized_coord.get_section("Current Work")
        assert work_items is not None

    def test_get_current_work_no_file(self, temp_project):
        """Test getting current work when file doesn't exist."""
        work_items = get_current_work(project_root=temp_project)
        assert work_items == []

    def test_get_blocked_items_empty(self, initialized_coord):
        """Test getting blocked items from template."""
        blocked = get_blocked_items(project_root=initialized_coord.project_root)
        # Template has one example
        assert len(blocked) >= 1

    def test_get_blocked_items_no_file(self, temp_project):
        """Test getting blocked items when file doesn't exist."""
        blocked = get_blocked_items(project_root=temp_project)
        assert blocked == []

    def test_get_review_queue_empty(self, initialized_coord):
        """Test getting review queue from template."""
        queue = get_review_queue(project_root=initialized_coord.project_root)
        # Template has one example
        assert len(queue) >= 1

    def test_get_review_queue_no_file(self, temp_project):
        """Test getting review queue when file doesn't exist."""
        queue = get_review_queue(project_root=temp_project)
        assert queue == []

    def test_get_decisions_empty(self, initialized_coord):
        """Test getting decisions from template."""
        decisions = get_decisions(project_root=initialized_coord.project_root)
        # Template has one example
        assert len(decisions) >= 1

    def test_get_decisions_no_file(self, temp_project):
        """Test getting decisions when file doesn't exist."""
        decisions = get_decisions(project_root=temp_project)
        assert decisions == []


class TestHelperFunctions:
    """Tests for helper functions to add items."""

    def test_add_current_work(self, temp_project):
        """Test adding a work item."""
        init_coordination_file(project_root=temp_project)

        result = add_current_work(
            agent="test-agent",
            task="Implement feature X",
            status="In Progress",
            agent_id="test-agent",
            project_root=temp_project,
        )

        assert result is True

        # Verify it was added
        work_items = get_current_work(project_root=temp_project)
        assert any("test-agent" in item and "Implement feature X" in item for item in work_items)

    def test_add_blocked_item(self, temp_project):
        """Test adding a blocked item."""
        init_coordination_file(project_root=temp_project)

        result = add_blocked_item(
            task="Feature Y",
            reason="Waiting for API",
            agent="test-agent",
            agent_id="test-agent",
            project_root=temp_project,
        )

        assert result is True

        # Verify it was added
        blocked = get_blocked_items(project_root=temp_project)
        assert any("Feature Y" in item and "Waiting for API" in item for item in blocked)

    def test_add_review_item(self, temp_project):
        """Test adding a review item."""
        init_coordination_file(project_root=temp_project)

        result = add_review_item(
            pr_number="#456",
            description="Add authentication",
            author="agent-1",
            reviewer="agent-2",
            agent_id="test-agent",
            project_root=temp_project,
        )

        assert result is True

        # Verify it was added
        reviews = get_review_queue(project_root=temp_project)
        assert any("#456" in item and "Add authentication" in item for item in reviews)

    def test_add_decision(self, temp_project):
        """Test adding a decision."""
        init_coordination_file(project_root=temp_project)

        result = add_decision(
            decision="Use PostgreSQL",
            rationale="Better performance for our use case",
            agent_id="test-agent",
            project_root=temp_project,
        )

        assert result is True

        # Verify it was added
        decisions = get_decisions(project_root=temp_project)
        assert any("Use PostgreSQL" in item for item in decisions)


class TestModuleLevelFunctions:
    """Tests for module-level convenience functions."""

    def test_init_coordination_file(self, temp_project):
        """Test module-level init function."""
        result = init_coordination_file(project_name="Module Test", project_root=temp_project)

        assert result is True
        coord_path = temp_project / COORDINATION_FILENAME
        assert coord_path.exists()

    def test_update_section_module_level(self, temp_project):
        """Test module-level update function."""
        init_coordination_file(project_root=temp_project)

        result = update_section(
            section="Sprint Goals",
            content="- Module level goal",
            agent_id="test-agent",
            project_root=temp_project,
        )

        assert result is True

    def test_get_section_module_level(self, temp_project):
        """Test module-level get section function."""
        init_coordination_file(project_root=temp_project)

        content = get_section("Sprint Goals", project_root=temp_project)
        assert content is not None


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_read_file_not_exists(self, coord_file):
        """Test reading file that doesn't exist."""
        with pytest.raises(FileNotFoundError):
            coord_file.read_file()

    def test_get_section_file_not_exists(self, coord_file):
        """Test getting section when file doesn't exist returns None."""
        result = coord_file.get_section("Sprint Goals")
        assert result is None

    def test_update_section_empty_name(self, initialized_coord):
        """Test updating section with empty name raises error."""
        with pytest.raises(ValueError, match="Section name cannot be empty"):
            update_section("", "content", agent_id="test-agent")

    def test_section_with_special_characters(self, initialized_coord):
        """Test section names with special characters."""
        section_name = "Special-Section_123"
        content = "Test content"

        result = initialized_coord.update_section(section_name, content)
        assert result is True

        retrieved = initialized_coord.get_section(section_name)
        assert retrieved == content

    def test_empty_section_content(self, initialized_coord):
        """Test updating section with empty content."""
        result = initialized_coord.update_section("Sprint Goals", "")
        assert result is True

        content = initialized_coord.get_section("Sprint Goals")
        assert content == ""

    def test_multiline_section_content(self, initialized_coord):
        """Test section with multiple lines."""
        multiline_content = """- Goal 1
- Goal 2
- Goal 3

Additional notes:
- Note 1
- Note 2"""

        result = initialized_coord.update_section("Sprint Goals", multiline_content)
        assert result is True

        retrieved = initialized_coord.get_section("Sprint Goals")
        assert retrieved == multiline_content

    def test_append_to_empty_section(self, temp_project):
        """Test appending to a section that doesn't exist yet."""
        coord = CoordinationFile(project_root=temp_project, agent_id="test-agent")
        coord.init_file()

        # Create a new section by appending
        result = coord.append_to_section("New Section", "First line")
        assert result is True

        content = coord.get_section("New Section")
        assert content == "First line"

        # Append another line
        result = coord.append_to_section("New Section", "Second line")
        assert result is True

        content = coord.get_section("New Section")
        assert "First line" in content
        assert "Second line" in content


class TestRebuildContent:
    """Tests for content rebuilding functionality."""

    def test_rebuild_maintains_structure(self, initialized_coord):
        """Test that rebuilding maintains file structure."""
        original_content = initialized_coord.read_file()
        sections = initialized_coord._parse_sections(original_content)

        # Rebuild without changes
        rebuilt = initialized_coord._rebuild_content(sections, original_content)

        # Should have all major sections
        assert "## Sprint Goals" in rebuilt
        assert "## Current Work" in rebuilt
        assert "## Blocked Items" in rebuilt

    def test_rebuild_with_modified_section(self, initialized_coord):
        """Test rebuilding with one modified section."""
        original_content = initialized_coord.read_file()
        sections = initialized_coord._parse_sections(original_content)

        # Modify one section
        sections["Sprint Goals"].content = "- Modified goal"

        rebuilt = initialized_coord._rebuild_content(sections, original_content)

        # Should contain modified content
        assert "- Modified goal" in rebuilt
        # Should still have other sections
        assert "## Current Work" in rebuilt
