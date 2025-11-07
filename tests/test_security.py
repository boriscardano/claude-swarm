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
