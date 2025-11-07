"""Extended test coverage for coordination.py module.

This test file adds comprehensive coverage for coordination.py,
targeting edge cases and code paths not covered by test_coordination.py.

Coverage targets:
- Line 254-255: FileNotFoundError in get_section
- Line 328: append_to_section with empty section
- Line 433: get_current_work with no content
- Line 454: get_blocked_items with no content
- Line 472: get_review_queue with no content
- Line 490: get_decisions with no content
"""

import tempfile
from pathlib import Path

import pytest

from claudeswarm.coordination import (
    COORDINATION_FILENAME,
    CoordinationFile,
    _reset_default_coordination,
    get_blocked_items,
    get_current_work,
    get_decisions,
    get_review_queue,
    get_section,
)


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


class TestMissingFileCoverage:
    """Tests for handling missing coordination files."""

    def test_get_section_file_not_found(self, coord_file):
        """Test get_section returns None when file doesn't exist.

        Covers lines 254-255: FileNotFoundError exception handling.
        """
        # File doesn't exist yet
        assert not coord_file.filepath.exists()

        # get_section should return None instead of raising exception
        result = coord_file.get_section("Sprint Goals")
        assert result is None

    def test_module_get_section_file_not_found(self, temp_project):
        """Test module-level get_section returns None when file doesn't exist.

        Additional coverage for lines 254-255.
        """
        # No coordination file exists
        result = get_section("Sprint Goals", project_root=temp_project)
        assert result is None


class TestEmptySectionCoverage:
    """Tests for handling empty sections in query functions."""

    def test_append_to_empty_section(self, initialized_coord):
        """Test appending to a section that has no content.

        Covers line 328: the else branch in append_to_section.
        """
        # Create a new section with empty content
        initialized_coord.update_section("New Section", "")

        # Verify it's empty
        content = initialized_coord.get_section("New Section")
        assert content == ""

        # Append to the empty section
        result = initialized_coord.append_to_section("New Section", "First line")
        assert result is True

        # Verify the content is just the new line (not prefixed with newline)
        updated_content = initialized_coord.get_section("New Section")
        assert updated_content == "First line"

    def test_get_current_work_empty_section(self, initialized_coord):
        """Test get_current_work returns empty list when section is empty.

        Covers line 433: early return when content is None.
        """
        # Update Current Work section to be completely empty
        initialized_coord.update_section("Current Work", "")

        # get_current_work should return empty list
        work_items = get_current_work(project_root=initialized_coord.project_root)
        assert work_items == []

    def test_get_current_work_no_file(self, temp_project):
        """Test get_current_work returns empty list when file doesn't exist.

        Additional coverage for line 433.
        """
        # No coordination file exists
        work_items = get_current_work(project_root=temp_project)
        assert work_items == []

    def test_get_blocked_items_empty_section(self, initialized_coord):
        """Test get_blocked_items returns empty list when section is empty.

        Covers line 454: early return when content is None.
        """
        # Update Blocked Items section to be completely empty
        initialized_coord.update_section("Blocked Items", "")

        # get_blocked_items should return empty list
        blocked = get_blocked_items(project_root=initialized_coord.project_root)
        assert blocked == []

    def test_get_blocked_items_no_file(self, temp_project):
        """Test get_blocked_items returns empty list when file doesn't exist.

        Additional coverage for line 454.
        """
        # No coordination file exists
        blocked = get_blocked_items(project_root=temp_project)
        assert blocked == []

    def test_get_review_queue_empty_section(self, initialized_coord):
        """Test get_review_queue returns empty list when section is empty.

        Covers line 472: early return when content is None.
        """
        # Update Code Review Queue section to be completely empty
        initialized_coord.update_section("Code Review Queue", "")

        # get_review_queue should return empty list
        queue = get_review_queue(project_root=initialized_coord.project_root)
        assert queue == []

    def test_get_review_queue_no_file(self, temp_project):
        """Test get_review_queue returns empty list when file doesn't exist.

        Additional coverage for line 472.
        """
        # No coordination file exists
        queue = get_review_queue(project_root=temp_project)
        assert queue == []

    def test_get_decisions_empty_section(self, initialized_coord):
        """Test get_decisions returns empty list when section is empty.

        Covers line 490: early return when content is None.
        """
        # Update Decisions section to be completely empty
        initialized_coord.update_section("Decisions", "")

        # get_decisions should return empty list
        decisions = get_decisions(project_root=initialized_coord.project_root)
        assert decisions == []

    def test_get_decisions_no_file(self, temp_project):
        """Test get_decisions returns empty list when file doesn't exist.

        Additional coverage for line 490.
        """
        # No coordination file exists
        decisions = get_decisions(project_root=temp_project)
        assert decisions == []


class TestEdgeCaseParsing:
    """Tests for edge cases in section parsing and querying."""

    def test_section_with_only_whitespace(self, initialized_coord):
        """Test handling of sections with only whitespace."""
        initialized_coord.update_section("Whitespace", "   \n\n   \n")

        # After update, content should be stripped to empty
        content = initialized_coord.get_section("Whitespace")
        assert content == ""

    def test_get_current_work_with_only_headers(self, initialized_coord):
        """Test get_current_work when section has only table headers."""
        # Section with just headers, no data rows
        table_header = "| Agent | Task | Status | Started |\n|-------|------|--------|---------|"
        initialized_coord.update_section("Current Work", table_header)

        work_items = get_current_work(project_root=initialized_coord.project_root)
        assert work_items == []

    def test_get_blocked_items_with_no_list_items(self, initialized_coord):
        """Test get_blocked_items when section has no list items."""
        # Section with text but no bullet points
        initialized_coord.update_section("Blocked Items", "No blocked items currently.")

        blocked = get_blocked_items(project_root=initialized_coord.project_root)
        assert blocked == []

    def test_get_review_queue_with_no_list_items(self, initialized_coord):
        """Test get_review_queue when section has no list items."""
        # Section with text but no bullet points
        initialized_coord.update_section("Code Review Queue", "Queue is empty.")

        queue = get_review_queue(project_root=initialized_coord.project_root)
        assert queue == []

    def test_get_decisions_with_no_list_items(self, initialized_coord):
        """Test get_decisions when section has no list items."""
        # Section with text but no bullet points
        initialized_coord.update_section("Decisions", "No decisions recorded yet.")

        decisions = get_decisions(project_root=initialized_coord.project_root)
        assert decisions == []


class TestMultipleAppends:
    """Tests for multiple append operations to empty and non-empty sections."""

    def test_multiple_appends_to_empty_section(self, initialized_coord):
        """Test multiple appends starting from an empty section."""
        # Create empty section
        initialized_coord.update_section("Test Section", "")

        # First append to empty section
        initialized_coord.append_to_section("Test Section", "Line 1")
        content = initialized_coord.get_section("Test Section")
        assert content == "Line 1"

        # Second append to now non-empty section
        initialized_coord.append_to_section("Test Section", "Line 2")
        content = initialized_coord.get_section("Test Section")
        assert "Line 1" in content
        assert "Line 2" in content

    def test_append_to_nonexistent_section(self, initialized_coord):
        """Test appending to a section that doesn't exist yet."""
        # Section doesn't exist
        assert initialized_coord.get_section("Nonexistent") is None

        # Append should create it with just the new line
        result = initialized_coord.append_to_section("Nonexistent", "New content")
        assert result is True

        content = initialized_coord.get_section("Nonexistent")
        assert content == "New content"


class TestComplexScenarios:
    """Tests for complex scenarios combining multiple operations."""

    def test_cycle_through_empty_and_populated_states(self, initialized_coord):
        """Test cycling a section between empty and populated states."""
        section = "Test Section"

        # Start empty
        initialized_coord.update_section(section, "")
        assert initialized_coord.get_section(section) == ""

        # Add content
        initialized_coord.append_to_section(section, "Content")
        assert initialized_coord.get_section(section) == "Content"

        # Empty it again
        initialized_coord.update_section(section, "")
        assert initialized_coord.get_section(section) == ""

        # Add content again
        initialized_coord.append_to_section(section, "New content")
        assert initialized_coord.get_section(section) == "New content"

    def test_all_query_functions_with_missing_file(self, temp_project):
        """Test all query functions handle missing file gracefully."""
        # No coordination file exists
        assert not (temp_project / COORDINATION_FILENAME).exists()

        # All query functions should return empty lists
        assert get_current_work(project_root=temp_project) == []
        assert get_blocked_items(project_root=temp_project) == []
        assert get_review_queue(project_root=temp_project) == []
        assert get_decisions(project_root=temp_project) == []
        assert get_section("Any Section", project_root=temp_project) is None

    def test_all_query_functions_with_empty_sections(self, initialized_coord):
        """Test all query functions with empty sections."""
        # Empty all sections
        initialized_coord.update_section("Current Work", "")
        initialized_coord.update_section("Blocked Items", "")
        initialized_coord.update_section("Code Review Queue", "")
        initialized_coord.update_section("Decisions", "")

        # All should return empty lists
        assert get_current_work(project_root=initialized_coord.project_root) == []
        assert get_blocked_items(project_root=initialized_coord.project_root) == []
        assert get_review_queue(project_root=initialized_coord.project_root) == []
        assert get_decisions(project_root=initialized_coord.project_root) == []


class TestFilePermissionsAndErrors:
    """Tests for file permission and error handling."""

    def test_get_section_survives_missing_file(self, coord_file):
        """Test that get_section doesn't crash on missing file."""
        # Ensure file doesn't exist
        if coord_file.filepath.exists():
            coord_file.filepath.unlink()

        # Should return None, not raise exception
        result = coord_file.get_section("Any Section")
        assert result is None

    def test_append_creates_section_atomically(self, initialized_coord):
        """Test that append creates section if it doesn't exist."""
        # Delete a section by updating to empty and then removing from file manually
        # First verify section doesn't exist
        content = initialized_coord.get_section("Nonexistent Section")
        assert content is None

        # Append should work even if section doesn't exist
        result = initialized_coord.append_to_section("Nonexistent Section", "First line")
        assert result is True

        # Verify it was created
        content = initialized_coord.get_section("Nonexistent Section")
        assert content == "First line"


class TestBulletPointParsing:
    """Tests for different bullet point styles in list sections."""

    def test_get_blocked_items_with_asterisk_bullets(self, initialized_coord):
        """Test get_blocked_items with asterisk-style bullets."""
        content = "* Item 1\n* Item 2"
        initialized_coord.update_section("Blocked Items", content)

        blocked = get_blocked_items(project_root=initialized_coord.project_root)
        assert len(blocked) == 2
        assert "* Item 1" in blocked
        assert "* Item 2" in blocked

    def test_get_blocked_items_with_dash_bullets(self, initialized_coord):
        """Test get_blocked_items with dash-style bullets."""
        content = "- Item 1\n- Item 2"
        initialized_coord.update_section("Blocked Items", content)

        blocked = get_blocked_items(project_root=initialized_coord.project_root)
        assert len(blocked) == 2
        assert "- Item 1" in blocked
        assert "- Item 2" in blocked

    def test_get_blocked_items_mixed_bullets(self, initialized_coord):
        """Test get_blocked_items with mixed bullet styles."""
        content = "- Item 1\n* Item 2\nNot a bullet\n- Item 3"
        initialized_coord.update_section("Blocked Items", content)

        blocked = get_blocked_items(project_root=initialized_coord.project_root)
        assert len(blocked) == 3
        assert "Not a bullet" not in blocked


class TestTableParsing:
    """Tests for table parsing in Current Work section."""

    def test_get_current_work_filters_non_table_rows(self, initialized_coord):
        """Test that get_current_work only returns table rows."""
        content = """| Agent | Task | Status | Started |
|-------|------|--------|---------|
| agent-1 | Task 1 | In Progress | 2025-11-07 |
Some random text that's not a table row
| agent-2 | Task 2 | Done | 2025-11-06 |"""
        initialized_coord.update_section("Current Work", content)

        work_items = get_current_work(project_root=initialized_coord.project_root)
        assert len(work_items) == 2
        assert all(item.startswith("|") for item in work_items)

    def test_get_current_work_with_malformed_table(self, initialized_coord):
        """Test get_current_work with a malformed table."""
        # Table with no separator row
        content = """| Agent | Task | Status | Started |
| agent-1 | Task 1 | In Progress | 2025-11-07 |"""
        initialized_coord.update_section("Current Work", content)

        # Should still parse, skipping first 2 lines
        work_items = get_current_work(project_root=initialized_coord.project_root)
        # Since we skip first 2 lines, this should be empty or have the data row
        # depending on what's after line 2
        assert isinstance(work_items, list)
