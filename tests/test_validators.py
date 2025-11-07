"""Tests for validation utilities.

This module tests all validation functions to ensure:
- Invalid inputs are rejected with helpful error messages
- Valid inputs are accepted and normalized correctly
- Edge cases are handled properly
- Security validations work correctly
"""

import pytest
from pathlib import Path
import tempfile
import os

from src.claudeswarm.validators import (
    ValidationError,
    validate_agent_id,
    validate_message_content,
    validate_file_path,
    validate_timeout,
    validate_retry_count,
    validate_rate_limit_config,
    validate_recipient_list,
    sanitize_message_content,
    normalize_path,
)


class TestAgentIDValidation:
    """Tests for agent ID validation."""

    def test_valid_agent_ids(self):
        """Test that valid agent IDs are accepted."""
        valid_ids = [
            "agent-1",
            "agent-2",
            "my_agent",
            "agent123",
            "a",
            "agent_1_2_3",
            "AGENT-1",
            "AgEnT-123",
        ]
        for agent_id in valid_ids:
            result = validate_agent_id(agent_id)
            assert result == agent_id.strip()

    def test_invalid_agent_ids(self):
        """Test that invalid agent IDs are rejected."""
        invalid_ids = [
            "",  # Empty
            "   ",  # Whitespace only
            "agent@123",  # Invalid character @
            "agent 1",  # Space
            "agent!",  # Invalid character !
            "agent.1",  # Invalid character .
            "agent/1",  # Invalid character /
            "-agent",  # Leading hyphen
            "agent-",  # Trailing hyphen
            "a" * 100,  # Too long
        ]
        for agent_id in invalid_ids:
            with pytest.raises(ValidationError):
                validate_agent_id(agent_id)

    def test_agent_id_type_validation(self):
        """Test that non-string types are rejected."""
        with pytest.raises(ValidationError, match="must be a string"):
            validate_agent_id(123)

        with pytest.raises(ValidationError, match="must be a string"):
            validate_agent_id(None)


class TestMessageContentValidation:
    """Tests for message content validation."""

    def test_valid_message_content(self):
        """Test that valid message content is accepted."""
        valid_messages = [
            "Hello, world!",
            "Multi-line\nmessage",
            "Unicode: 你好",
            "x" * 100,  # Short message
        ]
        for content in valid_messages:
            result = validate_message_content(content)
            assert result == content

    def test_empty_message_rejected(self):
        """Test that empty messages are rejected."""
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_message_content("")

        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_message_content("   ")

    def test_message_too_long(self):
        """Test that overly long messages are rejected."""
        # Default max is 10KB
        long_message = "x" * (10 * 1024 + 1)
        with pytest.raises(ValidationError, match="too long"):
            validate_message_content(long_message)

    def test_custom_length_limit(self):
        """Test custom length limits."""
        content = "x" * 100
        # Should pass with high limit
        validate_message_content(content, max_length=200)

        # Should fail with low limit
        with pytest.raises(ValidationError, match="too long"):
            validate_message_content(content, max_length=50)

    def test_message_type_validation(self):
        """Test that non-string types are rejected."""
        with pytest.raises(ValidationError, match="must be a string"):
            validate_message_content(123)


class TestFilePathValidation:
    """Tests for file path validation."""

    def test_valid_file_paths(self):
        """Test that valid file paths are accepted."""
        valid_paths = [
            "src/file.py",
            "/absolute/path/file.txt",
            "relative/path.txt",
            "simple.txt",
        ]
        for filepath in valid_paths:
            result = validate_file_path(filepath)
            assert isinstance(result, Path)

    def test_empty_path_rejected(self):
        """Test that empty paths are rejected."""
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_file_path("")

        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_file_path("   ")

    def test_path_traversal_detection(self):
        """Test that path traversal attempts are detected."""
        dangerous_paths = [
            "../../../etc/passwd",
            "src/../../etc/passwd",
            "..\\..\\windows\\system32",
        ]
        for filepath in dangerous_paths:
            # Match either "traversal" or "dangerous path pattern"
            with pytest.raises(ValidationError, match="(traversal|dangerous)"):
                validate_file_path(filepath, check_traversal=True)

    def test_path_traversal_can_be_disabled(self):
        """Test that path traversal check can be disabled."""
        # Should not raise when check is disabled
        result = validate_file_path("../file.py", check_traversal=False)
        assert isinstance(result, Path)

    def test_existence_check(self):
        """Test that existence check works."""
        # Create a temporary file
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            temp_path = tf.name

        try:
            # Should pass with must_exist=True
            result = validate_file_path(temp_path, must_exist=True)
            assert result.exists()

            # Non-existent file should fail
            with pytest.raises(ValidationError, match="does not exist"):
                validate_file_path("/nonexistent/file.txt", must_exist=True)
        finally:
            os.unlink(temp_path)

    def test_relative_path_requirement(self):
        """Test relative path requirement."""
        # Relative path should pass
        validate_file_path("relative/path.txt", must_be_relative=True)

        # Absolute path should fail
        with pytest.raises(ValidationError, match="must be relative"):
            validate_file_path("/absolute/path.txt", must_be_relative=True)

    def test_project_root_containment(self):
        """Test that paths can be restricted to project root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Path within project should pass
            validate_file_path("src/file.py", project_root=project_root)

            # Absolute path outside project should fail
            with pytest.raises(ValidationError, match="outside project root"):
                validate_file_path("/etc/passwd", project_root=project_root)


class TestTimeoutValidation:
    """Tests for timeout validation."""

    def test_valid_timeouts(self):
        """Test that valid timeouts are accepted."""
        valid_timeouts = [1, 10, 30, 60, 300, 3600]
        for timeout in valid_timeouts:
            result = validate_timeout(timeout)
            assert result == timeout

    def test_timeout_range_validation(self):
        """Test timeout range limits."""
        # Too small
        with pytest.raises(ValidationError, match="must be between"):
            validate_timeout(0)

        # Too large
        with pytest.raises(ValidationError, match="must be between"):
            validate_timeout(5000)

        # Negative
        with pytest.raises(ValidationError, match="must be between"):
            validate_timeout(-1)

    def test_custom_timeout_ranges(self):
        """Test custom timeout ranges."""
        # Should pass with custom range
        validate_timeout(5, min_val=1, max_val=10)

        # Should fail outside custom range
        with pytest.raises(ValidationError):
            validate_timeout(15, min_val=1, max_val=10)

    def test_timeout_type_conversion(self):
        """Test that timeouts are converted to int."""
        result = validate_timeout("30")
        assert result == 30
        assert isinstance(result, int)

        result = validate_timeout(30.5)
        assert result == 30


class TestRetryCountValidation:
    """Tests for retry count validation."""

    def test_valid_retry_counts(self):
        """Test that valid retry counts are accepted."""
        valid_counts = [0, 1, 2, 3, 5]
        for count in valid_counts:
            result = validate_retry_count(count)
            assert result == count

    def test_negative_retry_count_rejected(self):
        """Test that negative retry counts are rejected."""
        with pytest.raises(ValidationError, match="non-negative"):
            validate_retry_count(-1)

    def test_excessive_retry_count_rejected(self):
        """Test that excessive retry counts are rejected."""
        with pytest.raises(ValidationError, match="must not exceed"):
            validate_retry_count(10)

    def test_custom_max_retries(self):
        """Test custom max retries."""
        # Should pass with custom max
        validate_retry_count(8, max_retries=10)

        # Should fail with default max
        with pytest.raises(ValidationError):
            validate_retry_count(8, max_retries=5)


class TestRateLimitConfigValidation:
    """Tests for rate limit configuration validation."""

    def test_valid_rate_limit_config(self):
        """Test that valid configurations are accepted."""
        valid_configs = [
            (1, 1),
            (10, 60),
            (100, 300),
            (1000, 3600),
        ]
        for max_messages, window_seconds in valid_configs:
            result = validate_rate_limit_config(max_messages, window_seconds)
            assert result == (max_messages, window_seconds)

    def test_invalid_max_messages(self):
        """Test that invalid max_messages are rejected."""
        # Too small
        with pytest.raises(ValidationError, match="max_messages"):
            validate_rate_limit_config(0, 60)

        # Too large
        with pytest.raises(ValidationError, match="max_messages"):
            validate_rate_limit_config(2000, 60)

        # Negative
        with pytest.raises(ValidationError, match="max_messages"):
            validate_rate_limit_config(-1, 60)

    def test_invalid_window_seconds(self):
        """Test that invalid window_seconds are rejected."""
        # Too small
        with pytest.raises(ValidationError, match="window_seconds"):
            validate_rate_limit_config(10, 0)

        # Too large
        with pytest.raises(ValidationError, match="window_seconds"):
            validate_rate_limit_config(10, 5000)


class TestRecipientListValidation:
    """Tests for recipient list validation."""

    def test_valid_recipient_lists(self):
        """Test that valid recipient lists are accepted."""
        valid_lists = [
            ["agent-1"],
            ["agent-1", "agent-2"],
            ["agent-1", "agent-2", "agent-3"],
        ]
        for recipients in valid_lists:
            result = validate_recipient_list(recipients)
            assert result == recipients

    def test_empty_list_rejected(self):
        """Test that empty recipient lists are rejected."""
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_recipient_list([])

    def test_invalid_recipient_rejected(self):
        """Test that lists with invalid recipients are rejected."""
        with pytest.raises(ValidationError, match="Invalid recipient"):
            validate_recipient_list(["agent-1", "invalid@agent"])

    def test_duplicate_recipients_rejected(self):
        """Test that duplicate recipients are rejected."""
        with pytest.raises(ValidationError, match="Duplicate recipient"):
            validate_recipient_list(["agent-1", "agent-2", "agent-1"])

    def test_non_list_types_handled(self):
        """Test that tuples and sets are accepted."""
        # Tuple should work
        result = validate_recipient_list(("agent-1", "agent-2"))
        assert result == ["agent-1", "agent-2"]

        # Set should work (order may vary)
        result = validate_recipient_list({"agent-1", "agent-2"})
        assert set(result) == {"agent-1", "agent-2"}

    def test_invalid_container_type_rejected(self):
        """Test that non-iterable types are rejected."""
        with pytest.raises(ValidationError, match="must be a list"):
            validate_recipient_list("agent-1")


class TestMessageContentSanitization:
    """Tests for message content sanitization."""

    def test_null_bytes_removed(self):
        """Test that null bytes are removed."""
        content = "Hello\x00World"
        result = sanitize_message_content(content)
        assert "\x00" not in result
        assert result == "HelloWorld"

    def test_control_characters_removed(self):
        """Test that control characters are removed (except tab and newline)."""
        content = "Hello\x01\x02World"
        result = sanitize_message_content(content)
        assert "\x01" not in result
        assert "\x02" not in result

    def test_tabs_and_newlines_preserved(self):
        """Test that tabs and newlines are preserved."""
        content = "Line 1\nLine 2\tTabbed"
        result = sanitize_message_content(content)
        assert "\n" in result
        assert "\t" in result

    def test_line_endings_normalized(self):
        """Test that line endings are normalized."""
        content = "Line 1\r\nLine 2\rLine 3"
        result = sanitize_message_content(content)
        # All should become \n (but \r without \n may be stripped)
        assert "\r" not in result
        # At least one newline should exist
        assert "\n" in result

    def test_whitespace_trimmed(self):
        """Test that leading/trailing whitespace is trimmed."""
        content = "  Line 1  \n  Line 2  "
        result = sanitize_message_content(content)
        # Each line should have trailing whitespace removed
        assert result.startswith("Line 1")
        assert "Line 2" in result
        # Overall string should be trimmed
        assert not result.startswith("  ")
        assert not result.endswith("  ")


class TestPathNormalization:
    """Tests for cross-platform path normalization."""

    def test_forward_slashes_normalized(self):
        """Test that forward slashes are used consistently."""
        path = normalize_path("src/file.py")
        assert "/" in str(path) or "\\" not in str(path)

    def test_dot_segments_resolved(self):
        """Test that . segments are resolved."""
        path = normalize_path("src/./file.py")
        assert "/." not in str(path)

    def test_windows_style_paths(self):
        """Test that Windows-style paths are normalized."""
        # Note: On Unix, this becomes a filename with backslash
        # On Windows, it's normalized to forward slashes internally
        path = normalize_path("src\\file.py")
        assert isinstance(path, Path)


class TestValidationErrorMessages:
    """Tests that error messages are helpful and specific."""

    def test_agent_id_error_messages(self):
        """Test that agent ID errors are informative."""
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_agent_id("")

        with pytest.raises(ValidationError, match="invalid characters"):
            validate_agent_id("agent@123")

        with pytest.raises(ValidationError, match="too long"):
            validate_agent_id("a" * 100)

    def test_message_content_error_messages(self):
        """Test that message content errors are informative."""
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_message_content("")

        with pytest.raises(ValidationError, match="too long.*bytes"):
            validate_message_content("x" * 20000)

    def test_path_error_messages(self):
        """Test that path errors are informative."""
        with pytest.raises(ValidationError, match="traversal"):
            validate_file_path("../../../etc/passwd")

        with pytest.raises(ValidationError, match="does not exist"):
            validate_file_path("/nonexistent", must_exist=True)
