"""
Security-focused tests for Claude Swarm.

Tests cover:
- Command injection prevention in messaging
- Path traversal prevention in locking
- Message authentication with HMAC signatures

Author: Agent-Security
"""

import tempfile
from pathlib import Path
import pytest
from datetime import datetime

from claudeswarm.messaging import Message, MessageType, TmuxMessageDelivery
from claudeswarm.locking import LockManager


class TestCommandInjectionPrevention:
    """Tests for command injection prevention in messaging."""

    def test_escape_prevents_command_injection(self):
        """Test that escape_for_tmux prevents command injection."""
        # Attempt command injection with backticks
        malicious_text = "Hello; rm -rf /"
        escaped = TmuxMessageDelivery.escape_for_tmux(malicious_text)

        # The entire string should be safely quoted
        assert escaped.startswith("'")
        assert escaped.endswith("'")
        # The semicolon should be inside the quotes, not executed
        assert ";" in escaped

    def test_escape_prevents_backtick_injection(self):
        """Test that backtick command substitution is prevented."""
        malicious_text = "Message `whoami` here"
        escaped = TmuxMessageDelivery.escape_for_tmux(malicious_text)

        # Backticks should be safely quoted
        assert escaped.startswith("'")
        assert escaped.endswith("'")

    def test_escape_prevents_dollar_substitution(self):
        """Test that $() command substitution is prevented."""
        malicious_text = "Message $(cat /etc/passwd) here"
        escaped = TmuxMessageDelivery.escape_for_tmux(malicious_text)

        # $ should be safely quoted
        assert escaped.startswith("'")
        assert escaped.endswith("'")

    def test_escape_prevents_pipe_injection(self):
        """Test that pipe commands are prevented."""
        malicious_text = "Message | cat /etc/passwd"
        escaped = TmuxMessageDelivery.escape_for_tmux(malicious_text)

        # Pipe should be safely quoted
        assert escaped.startswith("'")
        assert escaped.endswith("'")


class TestPathTraversalPrevention:
    """Tests for path traversal prevention in locking."""

    def test_rejects_parent_directory_traversal(self):
        """Test that .. path traversal is rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "project"
            project_root.mkdir()

            lm = LockManager(project_root=project_root)

            # Attempt to lock file outside project using ..
            with pytest.raises(ValueError, match="Path traversal detected|outside project root"):
                lm.acquire_lock(
                    filepath="../../../etc/passwd",
                    agent_id="agent-1",
                    reason="malicious"
                )

    def test_rejects_absolute_path_outside_project(self):
        """Test that absolute paths outside project are rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "project"
            project_root.mkdir()

            lm = LockManager(project_root=project_root)

            # Attempt to lock file with absolute path outside project
            with pytest.raises(ValueError, match="outside project root"):
                lm.acquire_lock(
                    filepath="/etc/passwd",
                    agent_id="agent-1",
                    reason="malicious"
                )

    def test_allows_valid_relative_paths(self):
        """Test that valid relative paths within project are allowed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            lm = LockManager(project_root=project_root)

            # Valid relative path should work
            success, conflict = lm.acquire_lock(
                filepath="src/test.py",
                agent_id="agent-1",
                reason="legitimate lock"
            )

            assert success
            assert conflict is None

    def test_allows_valid_paths_with_subdirectories(self):
        """Test that valid paths with subdirectories are allowed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            lm = LockManager(project_root=project_root)

            # Valid path with subdirectories should work
            success, conflict = lm.acquire_lock(
                filepath="src/auth/login.py",
                agent_id="agent-1",
                reason="legitimate lock"
            )

            assert success
            assert conflict is None


class TestMonitoringCommandInjectionPrevention:
    """Tests for command injection prevention in monitoring dashboard."""

    def test_filter_type_validation_rejects_command_injection(self):
        """Test that command injection via filter_type is rejected."""
        from claudeswarm.monitoring import MessageType

        # Attempt command injection via filter_type - should raise ValueError
        malicious_filter = "INFO && rm -rf /"

        with pytest.raises(ValueError):
            MessageType(malicious_filter)

    def test_filter_type_validation_rejects_shell_metacharacters(self):
        """Test that shell metacharacters in filter_type are rejected."""
        from claudeswarm.monitoring import MessageType

        # Various shell injection attempts - all should raise ValueError
        malicious_inputs = [
            "; ls -la",
            "| cat /etc/passwd",
            "$(whoami)",
            "`id`",
            "INFO; malicious-command",
            "INFO && malicious",
            "INFO || malicious",
        ]

        for malicious in malicious_inputs:
            with pytest.raises(ValueError):
                MessageType(malicious)

    def test_filter_agent_validation_rejects_shell_metacharacters(self):
        """Test that shell metacharacters in filter_agent are rejected."""
        from claudeswarm.validators import ValidationError, validate_agent_id

        # Attempt command injection via filter_agent
        malicious_agents = [
            "agent-1; rm -rf /",
            "agent$(whoami)",
            "agent`id`",
            "agent | ls",
            "agent && malicious",
            "agent@malicious",  # @ not allowed
            "agent.malicious",  # . not allowed
            "../../../etc/passwd",
        ]

        for malicious in malicious_agents:
            # Should raise ValidationError
            with pytest.raises(ValidationError):
                validate_agent_id(malicious)

    def test_valid_filter_type_passes_validation(self):
        """Test that valid MessageType values pass validation."""
        from claudeswarm.monitoring import MessageFilter, MessageType

        # All valid MessageType values should work
        valid_types = ["INFO", "QUESTION", "BLOCKED", "COMPLETED", "ACK", "CHALLENGE", "REVIEW-REQUEST"]

        for msg_type in valid_types:
            msg_filter = MessageFilter()
            # Should not raise any exception
            try:
                msg_filter.msg_types = {MessageType(msg_type)}
            except Exception as e:
                pytest.fail(f"Valid message type '{msg_type}' was rejected: {e}")

    def test_valid_filter_agent_passes_validation(self):
        """Test that valid agent IDs pass validation."""
        from claudeswarm.validators import validate_agent_id

        # Valid agent IDs (alphanumeric, hyphens, underscores)
        valid_agents = [
            "agent-1",
            "agent_2",
            "my-agent-123",
            "AgentABC",
            "test_agent_456",
        ]

        for agent_id in valid_agents:
            # Should not raise ValidationError
            try:
                validate_agent_id(agent_id)
            except Exception as e:
                pytest.fail(f"Valid agent ID '{agent_id}' was rejected: {e}")

    def test_shlex_quote_escapes_dangerous_characters(self):
        """Test that shlex.quote properly escapes shell metacharacters."""
        import shlex

        dangerous_inputs = [
            "; rm -rf /",
            "$(malicious)",
            "`malicious`",
            "| cat /etc/passwd",
            "&& malicious",
            "|| malicious",
            "> /tmp/evil",
            "< /etc/passwd",
        ]

        for dangerous in dangerous_inputs:
            quoted = shlex.quote(dangerous)

            # The quoted string should be safe - either wrapped in single quotes
            # or have dangerous characters escaped
            assert quoted.startswith("'") or "\\" in quoted

            # When unquoted in a shell, it should be treated as a literal string
            # not as a command


class TestMessageAuthentication:
    """Tests for HMAC message authentication."""

    def test_message_has_signature_after_signing(self):
        """Test that signing adds a signature to the message."""
        msg = Message(
            sender_id="agent-1",
            timestamp=datetime.now(),
            msg_type=MessageType.INFO,
            content="Test message",
            recipients=["agent-2"]
        )

        # Initially no signature
        assert msg.signature == ""

        # Sign the message
        msg.sign()

        # Should now have a signature
        assert msg.signature != ""
        assert len(msg.signature) > 0

    def test_signature_verification_succeeds_for_valid_message(self):
        """Test that signature verification succeeds for valid messages."""
        msg = Message(
            sender_id="agent-1",
            timestamp=datetime.now(),
            msg_type=MessageType.INFO,
            content="Test message",
            recipients=["agent-2"]
        )

        msg.sign()

        # Verification should succeed
        assert msg.verify_signature() is True

    def test_signature_verification_fails_for_tampered_content(self):
        """Test that signature verification fails if content is tampered."""
        msg = Message(
            sender_id="agent-1",
            timestamp=datetime.now(),
            msg_type=MessageType.INFO,
            content="Original message",
            recipients=["agent-2"]
        )

        msg.sign()

        # Tamper with content
        msg.content = "Tampered message"

        # Verification should fail
        assert msg.verify_signature() is False

    def test_signature_verification_fails_for_tampered_sender(self):
        """Test that signature verification fails if sender is tampered."""
        msg = Message(
            sender_id="agent-1",
            timestamp=datetime.now(),
            msg_type=MessageType.INFO,
            content="Test message",
            recipients=["agent-2"]
        )

        msg.sign()

        # Tamper with sender
        msg.sender_id = "agent-3"

        # Verification should fail
        assert msg.verify_signature() is False

    def test_signature_is_included_in_serialization(self):
        """Test that signature is included in to_dict() output."""
        msg = Message(
            sender_id="agent-1",
            timestamp=datetime.now(),
            msg_type=MessageType.INFO,
            content="Test message",
            recipients=["agent-2"]
        )

        msg.sign()

        msg_dict = msg.to_dict()

        assert "signature" in msg_dict
        assert msg_dict["signature"] == msg.signature

    def test_signature_is_restored_from_deserialization(self):
        """Test that signature is restored from from_dict()."""
        msg = Message(
            sender_id="agent-1",
            timestamp=datetime.now(),
            msg_type=MessageType.INFO,
            content="Test message",
            recipients=["agent-2"]
        )

        msg.sign()
        original_signature = msg.signature

        # Serialize and deserialize
        msg_dict = msg.to_dict()
        restored_msg = Message.from_dict(msg_dict)

        # Signature should be preserved
        assert restored_msg.signature == original_signature
        assert restored_msg.verify_signature() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
