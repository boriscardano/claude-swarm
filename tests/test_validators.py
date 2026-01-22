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
    validate_host,
    validate_port,
    sanitize_message_content,
    normalize_path,
    contains_dangerous_unicode,
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

    def test_bidirectional_override_removed(self):
        """Test that bidirectional override characters are removed."""
        # RIGHT-TO-LEFT OVERRIDE
        content = "Hello\u202EWorld"
        result = sanitize_message_content(content)
        assert "\u202E" not in result
        assert result == "HelloWorld"

        # LEFT-TO-RIGHT EMBEDDING
        content = "Test\u202ACode"
        result = sanitize_message_content(content)
        assert "\u202A" not in result
        assert result == "TestCode"

        # Multiple bidi characters
        content = "\u202DHello\u202EWorld\u202C"
        result = sanitize_message_content(content)
        assert "\u202D" not in result
        assert "\u202E" not in result
        assert "\u202C" not in result
        assert result == "HelloWorld"

    def test_zero_width_characters_removed(self):
        """Test that zero-width characters are removed."""
        # ZERO WIDTH SPACE
        content = "Hello\u200BWorld"
        result = sanitize_message_content(content)
        assert "\u200B" not in result
        assert result == "HelloWorld"

        # ZERO WIDTH NON-JOINER
        content = "Test\u200CCode"
        result = sanitize_message_content(content)
        assert "\u200C" not in result
        assert result == "TestCode"

        # ZERO WIDTH JOINER
        content = "My\u200DText"
        result = sanitize_message_content(content)
        assert "\u200D" not in result
        assert result == "MyText"

        # WORD JOINER
        content = "Some\u2060Text"
        result = sanitize_message_content(content)
        assert "\u2060" not in result
        assert result == "SomeText"

        # ZERO WIDTH NO-BREAK SPACE (BOM)
        content = "\uFEFFHello"
        result = sanitize_message_content(content)
        assert "\uFEFF" not in result
        assert result == "Hello"

    def test_normal_unicode_preserved(self):
        """Test that normal Unicode characters (emojis, international) are preserved."""
        # Emojis
        content = "Hello 👋 World 🌍"
        result = sanitize_message_content(content)
        assert "👋" in result
        assert "🌍" in result

        # Chinese characters
        content = "你好世界"
        result = sanitize_message_content(content)
        assert result == "你好世界"

        # Arabic
        content = "مرحبا"
        result = sanitize_message_content(content)
        assert result == "مرحبا"

        # Cyrillic
        content = "Привет"
        result = sanitize_message_content(content)
        assert result == "Привет"

        # Japanese
        content = "こんにちは"
        result = sanitize_message_content(content)
        assert result == "こんにちは"

    def test_mixed_dangerous_and_safe_unicode(self):
        """Test content with both dangerous and safe Unicode."""
        # Mix of emoji and bidi override
        content = "Hello 👋\u202E World"
        result = sanitize_message_content(content)
        assert "👋" in result
        assert "\u202E" not in result
        assert "Hello" in result
        assert "World" in result

        # Mix of international text and zero-width
        content = "你好\u200B世界"
        result = sanitize_message_content(content)
        assert "你好" in result
        assert "世界" in result
        assert "\u200B" not in result

    def test_trojan_source_attack_prevented(self):
        """Test prevention of Trojan Source attack (CVE-2021-42574)."""
        # Example of a potential attack where code appears different than it executes
        # The bidi override can make "/* comment */" look like code
        malicious_content = "access = \u202Efalse\u202C = true"
        result = sanitize_message_content(malicious_content)
        # All bidi characters should be removed
        assert "\u202E" not in result
        assert "\u202C" not in result
        # Content should be readable left-to-right
        assert "access = false = true" in result or "access =  = true" in result


class TestDangerousUnicodeDetection:
    """Tests for dangerous Unicode detection function."""

    def test_no_dangerous_unicode(self):
        """Test detection with safe text."""
        has_dangerous, found = contains_dangerous_unicode("Hello World")
        assert has_dangerous is False
        assert len(found) == 0

    def test_detect_bidi_override(self):
        """Test detection of bidirectional override characters."""
        # RIGHT-TO-LEFT OVERRIDE
        has_dangerous, found = contains_dangerous_unicode("Hello\u202EWorld")
        assert has_dangerous is True
        assert len(found) > 0
        assert any("RIGHT-TO-LEFT OVERRIDE" in name for name in found)

        # LEFT-TO-RIGHT EMBEDDING
        has_dangerous, found = contains_dangerous_unicode("Test\u202ACode")
        assert has_dangerous is True
        assert len(found) > 0

    def test_detect_zero_width_chars(self):
        """Test detection of zero-width characters."""
        # ZERO WIDTH SPACE
        has_dangerous, found = contains_dangerous_unicode("Hello\u200BWorld")
        assert has_dangerous is True
        assert len(found) > 0
        assert any("ZERO WIDTH SPACE" in name for name in found)

        # ZERO WIDTH NON-JOINER
        has_dangerous, found = contains_dangerous_unicode("Test\u200CCode")
        assert has_dangerous is True
        assert len(found) > 0

    def test_detect_multiple_dangerous_chars(self):
        """Test detection of multiple dangerous characters."""
        text = "Hello\u202E\u200BWorld"
        has_dangerous, found = contains_dangerous_unicode(text)
        assert has_dangerous is True
        assert len(found) >= 2

    def test_normal_unicode_not_flagged(self):
        """Test that normal Unicode (emojis, international) is not flagged."""
        # Emojis
        has_dangerous, found = contains_dangerous_unicode("Hello 👋 World")
        assert has_dangerous is False
        assert len(found) == 0

        # Chinese
        has_dangerous, found = contains_dangerous_unicode("你好世界")
        assert has_dangerous is False
        assert len(found) == 0

        # Arabic
        has_dangerous, found = contains_dangerous_unicode("مرحبا")
        assert has_dangerous is False
        assert len(found) == 0

    def test_character_names_reported(self):
        """Test that character names are properly reported."""
        text = "Test\u202ECode"
        has_dangerous, found = contains_dangerous_unicode(text)
        assert has_dangerous is True
        assert len(found) == 1
        # Should contain human-readable name
        assert "RIGHT-TO-LEFT OVERRIDE" in found[0]


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


class TestHostValidation:
    """Tests for host/IP validation."""

    def test_valid_hostnames(self):
        """Test that valid hostnames are accepted."""
        valid_hosts = [
            "localhost",
            "example.com",
            "sub.example.com",
            "api-server.example.com",
            "server1",
            "my-server-123",
        ]
        for host in valid_hosts:
            result = validate_host(host)
            assert result == host

    def test_valid_ipv4_addresses(self):
        """Test that valid IPv4 addresses are accepted."""
        valid_ips = [
            "127.0.0.1",
            "192.168.1.1",
            "10.0.0.1",
            "172.16.0.1",
        ]
        for ip in valid_ips:
            result = validate_host(ip)
            assert result == ip

    def test_valid_ipv6_addresses(self):
        """Test that valid IPv6 addresses are accepted."""
        valid_ips = [
            "::1",
            "fe80::1",
            "2001:db8::1",
            "2001:0db8:85a3:0000:0000:8a2e:0370:7334",
        ]
        for ip in valid_ips:
            result = validate_host(ip)
            assert result == ip

    def test_invalid_hostnames(self):
        """Test that invalid hostnames are rejected."""
        invalid_hosts = [
            "",  # Empty
            "   ",  # Whitespace only
            "host@name",  # Invalid character
            "host name",  # Space
            "-hostname",  # Leading hyphen
            "hostname-",  # Trailing hyphen
            "host..name",  # Double dot
            "a" * 300,  # Too long
        ]
        for host in invalid_hosts:
            with pytest.raises(ValidationError):
                validate_host(host)

    def test_all_interfaces_warning(self):
        """Test that binding to all interfaces triggers a warning."""
        warnings = []

        def capture_warning(msg: str):
            warnings.append(msg)

        # Test 0.0.0.0 without allow_all_interfaces
        validate_host("0.0.0.0", allow_all_interfaces=False, warn_callback=capture_warning)
        assert len(warnings) == 1
        assert "all network interfaces" in warnings[0]

        # Test :: (IPv6 all interfaces)
        warnings.clear()
        validate_host("::", allow_all_interfaces=False, warn_callback=capture_warning)
        assert len(warnings) == 1
        assert "all network interfaces" in warnings[0]

    def test_all_interfaces_allowed(self):
        """Test that all-interfaces binding can be explicitly allowed."""
        warnings = []

        def capture_warning(msg: str):
            warnings.append(msg)

        # Should not warn when explicitly allowed
        validate_host("0.0.0.0", allow_all_interfaces=True, warn_callback=capture_warning)
        assert len(warnings) == 0

        validate_host("::", allow_all_interfaces=True, warn_callback=capture_warning)
        assert len(warnings) == 0

    def test_public_ip_warning(self):
        """Test that public IP addresses trigger warnings."""
        warnings = []

        def capture_warning(msg: str):
            warnings.append(msg)

        # Test a public IP (e.g., Google DNS)
        validate_host("8.8.8.8", warn_callback=capture_warning)
        assert len(warnings) == 1
        assert "public IP address" in warnings[0]

    def test_private_ip_no_warning(self):
        """Test that private IPs don't trigger public IP warnings."""
        warnings = []

        def capture_warning(msg: str):
            warnings.append(msg)

        # Private IPs should not warn about being public
        private_ips = ["127.0.0.1", "192.168.1.1", "10.0.0.1", "172.16.0.1"]
        for ip in private_ips:
            warnings.clear()
            validate_host(ip, warn_callback=capture_warning)
            # Should have no warnings (not public IPs)
            public_warnings = [w for w in warnings if "public IP" in w]
            assert len(public_warnings) == 0

    def test_host_type_validation(self):
        """Test that non-string types are rejected."""
        with pytest.raises(ValidationError, match="must be a non-empty string"):
            validate_host(None)

        with pytest.raises(ValidationError, match="must be a non-empty string"):
            validate_host(123)


class TestPortValidation:
    """Tests for port number validation."""

    def test_valid_ports(self):
        """Test that valid port numbers are accepted."""
        valid_ports = [1, 80, 443, 8080, 3000, 5000, 65535]
        for port in valid_ports:
            result = validate_port(port)
            assert result == port
            assert isinstance(result, int)

    def test_port_range_validation(self):
        """Test port range limits."""
        # Too small
        with pytest.raises(ValidationError, match="must be between 1 and 65535"):
            validate_port(0)

        # Too large
        with pytest.raises(ValidationError, match="must be between 1 and 65535"):
            validate_port(65536)

        # Negative
        with pytest.raises(ValidationError, match="must be between 1 and 65535"):
            validate_port(-1)

    def test_port_type_conversion(self):
        """Test that ports are converted to int."""
        result = validate_port("8080")
        assert result == 8080
        assert isinstance(result, int)

        result = validate_port(8080.5)
        assert result == 8080
        assert isinstance(result, int)

    def test_port_type_validation(self):
        """Test that invalid types are rejected."""
        with pytest.raises(ValidationError, match="must be an integer"):
            validate_port("invalid")

        with pytest.raises(ValidationError, match="must be an integer"):
            validate_port(None)

    def test_privileged_ports_parameter(self):
        """Test that allow_privileged parameter is accepted."""
        # Currently, allow_privileged doesn't affect validation,
        # but the parameter should be accepted for future use
        result = validate_port(80, allow_privileged=True)
        assert result == 80

        result = validate_port(80, allow_privileged=False)
        assert result == 80


class TestHostPortIntegration:
    """Integration tests for host and port validation together."""

    def test_common_server_configurations(self):
        """Test common server configurations."""
        configs = [
            ("localhost", 8080),
            ("127.0.0.1", 3000),
            ("0.0.0.0", 8000),
            ("example.com", 443),
        ]

        for host, port in configs:
            validated_host = validate_host(host, allow_all_interfaces=True)
            validated_port = validate_port(port)
            assert validated_host == host
            assert validated_port == port

    def test_invalid_configurations(self):
        """Test that invalid configurations are rejected."""
        # Invalid host
        with pytest.raises(ValidationError):
            validate_host("invalid@host")

        # Invalid port
        with pytest.raises(ValidationError):
            validate_port(0)

        with pytest.raises(ValidationError):
            validate_port(70000)
