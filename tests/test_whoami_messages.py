"""
Comprehensive tests for whoami command message display functionality.

This test module covers:
- Whoami shows recent messages
- Message limit of 3
- Graceful handling when MessageLogger fails
- Integration with whoami command

Author: Test Coverage Enhancement
"""

import json
import os
from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from claudeswarm.cli import WHOAMI_MESSAGE_PREVIEW_LIMIT, cmd_whoami
from claudeswarm.messaging import Message, MessageLogger, MessageType


class TestWhoamiMessageDisplay:
    """Tests for whoami command message display functionality."""

    @patch("claudeswarm.cli.get_active_agents_path")
    @patch("subprocess.run")
    def test_whoami_shows_recent_messages(self, mock_subprocess, mock_get_path, tmp_path, capsys):
        """Test that whoami shows recent messages."""
        import argparse

        # Setup tmux environment
        os.environ["TMUX_PANE"] = "%1"

        # Mock subprocess to return pane info
        mock_subprocess.return_value = Mock(returncode=0, stdout="main:0.0\n", stderr="")

        # Create agent registry
        registry_path = tmp_path / "active_agents.json"
        mock_get_path.return_value = registry_path

        agent_data = {
            "session_name": "main",
            "updated_at": datetime.now().isoformat(),
            "agents": [
                {
                    "id": "agent-1",
                    "pane_index": "main:0.0",
                    "pid": 12345,
                    "status": "active",
                    "last_seen": datetime.now().isoformat(),
                    "session_name": "main",
                    "tmux_pane_id": "%1",
                }
            ],
        }

        with open(registry_path, "w") as f:
            json.dump(agent_data, f)

        # Create message log with messages
        log_file = tmp_path / "agent_messages.log"
        with open(log_file, "w") as f:
            for i in range(5):
                msg = {
                    "sender": f"agent-{i}",
                    "timestamp": datetime.now().isoformat(),
                    "msg_type": "INFO",
                    "content": f"Message {i}",
                    "recipients": ["agent-1"],
                    "msg_id": f"msg-{i}",
                }
                f.write(json.dumps(msg) + "\n")

        # Mock MessageLogger to use our test log file
        with patch("claudeswarm.messaging.get_messages_log_path", return_value=log_file):
            args = argparse.Namespace()

            with pytest.raises(SystemExit) as exc_info:
                cmd_whoami(args)

            assert exc_info.value.code == 0

            captured = capsys.readouterr()

            # Verify agent info is shown
            assert "Agent ID: agent-1" in captured.out
            assert "You ARE registered as an active agent" in captured.out

            # Verify messages section is shown
            assert "RECENT MESSAGES" in captured.out

            # Should show at most 3 recent messages (limit)
            assert (
                "Message 2" in captured.out
                or "Message 3" in captured.out
                or "Message 4" in captured.out
            )

        # Cleanup
        if "TMUX_PANE" in os.environ:
            del os.environ["TMUX_PANE"]

    @patch("claudeswarm.cli.get_active_agents_path")
    @patch("subprocess.run")
    def test_whoami_message_limit_of_3(self, mock_subprocess, mock_get_path, tmp_path, capsys):
        """Test limit of 3 messages is enforced."""
        import argparse

        os.environ["TMUX_PANE"] = "%1"

        mock_subprocess.return_value = Mock(returncode=0, stdout="main:0.0\n", stderr="")

        registry_path = tmp_path / "active_agents.json"
        mock_get_path.return_value = registry_path

        agent_data = {
            "session_name": "main",
            "updated_at": datetime.now().isoformat(),
            "agents": [
                {
                    "id": "agent-1",
                    "pane_index": "main:0.0",
                    "pid": 12345,
                    "status": "active",
                    "last_seen": datetime.now().isoformat(),
                    "session_name": "main",
                    "tmux_pane_id": "%1",
                }
            ],
        }

        with open(registry_path, "w") as f:
            json.dump(agent_data, f)

        # Create message log with 10 messages
        log_file = tmp_path / "agent_messages.log"
        with open(log_file, "w") as f:
            for i in range(10):
                msg = {
                    "sender": f"agent-sender-{i}",
                    "timestamp": datetime.now().isoformat(),
                    "msg_type": "INFO",
                    "content": f"Test message number {i}",
                    "recipients": ["agent-1"],
                    "msg_id": f"msg-{i}",
                }
                f.write(json.dumps(msg) + "\n")

        with patch("claudeswarm.messaging.get_messages_log_path", return_value=log_file):
            args = argparse.Namespace()

            with pytest.raises(SystemExit):
                cmd_whoami(args)

            captured = capsys.readouterr()

            # Should show the 3 most recent messages (7, 8, 9)
            assert "Test message number 7" in captured.out
            assert "Test message number 8" in captured.out
            assert "Test message number 9" in captured.out

            # Should NOT show older messages (0-6)
            assert "Test message number 0" not in captured.out
            assert "Test message number 6" not in captured.out

            # Should show limit indicator
            assert f"Showing {WHOAMI_MESSAGE_PREVIEW_LIMIT} most recent" in captured.out

        if "TMUX_PANE" in os.environ:
            del os.environ["TMUX_PANE"]

    @patch("claudeswarm.cli.get_active_agents_path")
    @patch("subprocess.run")
    def test_whoami_graceful_handling_when_no_messages(
        self, mock_subprocess, mock_get_path, tmp_path, capsys
    ):
        """Test graceful handling when there are no messages."""
        import argparse

        os.environ["TMUX_PANE"] = "%1"

        mock_subprocess.return_value = Mock(returncode=0, stdout="main:0.0\n", stderr="")

        registry_path = tmp_path / "active_agents.json"
        mock_get_path.return_value = registry_path

        agent_data = {
            "session_name": "main",
            "updated_at": datetime.now().isoformat(),
            "agents": [
                {
                    "id": "agent-1",
                    "pane_index": "main:0.0",
                    "pid": 12345,
                    "status": "active",
                    "last_seen": datetime.now().isoformat(),
                    "session_name": "main",
                    "tmux_pane_id": "%1",
                }
            ],
        }

        with open(registry_path, "w") as f:
            json.dump(agent_data, f)

        # Create empty message log
        log_file = tmp_path / "agent_messages.log"
        log_file.touch()

        with patch("claudeswarm.messaging.get_messages_log_path", return_value=log_file):
            args = argparse.Namespace()

            with pytest.raises(SystemExit):
                cmd_whoami(args)

            captured = capsys.readouterr()

            # Should show "No messages"
            assert "No messages" in captured.out

        if "TMUX_PANE" in os.environ:
            del os.environ["TMUX_PANE"]

    @patch("claudeswarm.cli.get_active_agents_path")
    @patch("subprocess.run")
    def test_whoami_graceful_handling_when_logger_fails(
        self, mock_subprocess, mock_get_path, tmp_path, capsys
    ):
        """Test graceful handling when MessageLogger fails."""
        import argparse

        os.environ["TMUX_PANE"] = "%1"

        mock_subprocess.return_value = Mock(returncode=0, stdout="main:0.0\n", stderr="")

        registry_path = tmp_path / "active_agents.json"
        mock_get_path.return_value = registry_path

        agent_data = {
            "session_name": "main",
            "updated_at": datetime.now().isoformat(),
            "agents": [
                {
                    "id": "agent-1",
                    "pane_index": "main:0.0",
                    "pid": 12345,
                    "status": "active",
                    "last_seen": datetime.now().isoformat(),
                    "session_name": "main",
                    "tmux_pane_id": "%1",
                }
            ],
        }

        with open(registry_path, "w") as f:
            json.dump(agent_data, f)

        # Mock MessageLogger to raise an exception
        with patch("claudeswarm.cli.MessageLogger") as mock_logger_class:
            mock_logger_instance = Mock()
            mock_logger_instance.get_messages_for_agent.side_effect = Exception("Test error")
            mock_logger_class.return_value = mock_logger_instance

            args = argparse.Namespace()

            # Should not crash, should exit cleanly
            with pytest.raises(SystemExit) as exc_info:
                cmd_whoami(args)

            assert exc_info.value.code == 0

            captured = capsys.readouterr()

            # Should still show agent info
            assert "Agent ID: agent-1" in captured.out

            # Should show error message gracefully
            assert "Could not check messages" in captured.out

        if "TMUX_PANE" in os.environ:
            del os.environ["TMUX_PANE"]

    @patch("claudeswarm.cli.get_active_agents_path")
    @patch("subprocess.run")
    def test_whoami_message_display_format(self, mock_subprocess, mock_get_path, tmp_path, capsys):
        """Test message display format is correct."""
        import argparse

        os.environ["TMUX_PANE"] = "%1"

        mock_subprocess.return_value = Mock(returncode=0, stdout="main:0.0\n", stderr="")

        registry_path = tmp_path / "active_agents.json"
        mock_get_path.return_value = registry_path

        agent_data = {
            "session_name": "main",
            "updated_at": datetime.now().isoformat(),
            "agents": [
                {
                    "id": "agent-1",
                    "pane_index": "main:0.0",
                    "pid": 12345,
                    "status": "active",
                    "last_seen": datetime.now().isoformat(),
                    "session_name": "main",
                    "tmux_pane_id": "%1",
                }
            ],
        }

        with open(registry_path, "w") as f:
            json.dump(agent_data, f)

        # Create message log with specific content
        log_file = tmp_path / "agent_messages.log"
        timestamp = "2025-11-18T14:30:00.123456"
        with open(log_file, "w") as f:
            msg = {
                "sender": "agent-coordinator",
                "timestamp": timestamp,
                "msg_type": "QUESTION",
                "content": "What is your status?",
                "recipients": ["agent-1"],
                "msg_id": "msg-123",
            }
            f.write(json.dumps(msg) + "\n")

        with patch("claudeswarm.messaging.get_messages_log_path", return_value=log_file):
            args = argparse.Namespace()

            with pytest.raises(SystemExit):
                cmd_whoami(args)

            captured = capsys.readouterr()

            # Verify message format includes timestamp (trimmed), sender, and type
            assert "2025-11-18T14:30:00" in captured.out
            assert "From: agent-coordinator" in captured.out
            assert "QUESTION" in captured.out
            assert "What is your status?" in captured.out

        if "TMUX_PANE" in os.environ:
            del os.environ["TMUX_PANE"]

    @patch("claudeswarm.cli.get_active_agents_path")
    @patch("subprocess.run")
    def test_whoami_shows_commands_available(
        self, mock_subprocess, mock_get_path, tmp_path, capsys
    ):
        """Test that whoami shows available commands."""
        import argparse

        os.environ["TMUX_PANE"] = "%1"

        mock_subprocess.return_value = Mock(returncode=0, stdout="main:0.0\n", stderr="")

        registry_path = tmp_path / "active_agents.json"
        mock_get_path.return_value = registry_path

        agent_data = {
            "session_name": "main",
            "updated_at": datetime.now().isoformat(),
            "agents": [
                {
                    "id": "agent-1",
                    "pane_index": "main:0.0",
                    "pid": 12345,
                    "status": "active",
                    "last_seen": datetime.now().isoformat(),
                    "session_name": "main",
                    "tmux_pane_id": "%1",
                }
            ],
        }

        with open(registry_path, "w") as f:
            json.dump(agent_data, f)

        log_file = tmp_path / "agent_messages.log"
        log_file.touch()

        with patch("claudeswarm.messaging.get_messages_log_path", return_value=log_file):
            args = argparse.Namespace()

            with pytest.raises(SystemExit):
                cmd_whoami(args)

            captured = capsys.readouterr()

            # Verify command list is shown
            assert "Commands available" in captured.out
            assert "check-messages" in captured.out
            assert "send-message" in captured.out
            assert "broadcast-message" in captured.out
            assert "acquire-file-lock" in captured.out

        if "TMUX_PANE" in os.environ:
            del os.environ["TMUX_PANE"]

    @patch("claudeswarm.cli.get_active_agents_path")
    @patch("subprocess.run")
    def test_whoami_with_multiple_message_types(
        self, mock_subprocess, mock_get_path, tmp_path, capsys
    ):
        """Test whoami displays different message types correctly."""
        import argparse

        os.environ["TMUX_PANE"] = "%1"

        mock_subprocess.return_value = Mock(returncode=0, stdout="main:0.0\n", stderr="")

        registry_path = tmp_path / "active_agents.json"
        mock_get_path.return_value = registry_path

        agent_data = {
            "session_name": "main",
            "updated_at": datetime.now().isoformat(),
            "agents": [
                {
                    "id": "agent-1",
                    "pane_index": "main:0.0",
                    "pid": 12345,
                    "status": "active",
                    "last_seen": datetime.now().isoformat(),
                    "session_name": "main",
                    "tmux_pane_id": "%1",
                }
            ],
        }

        with open(registry_path, "w") as f:
            json.dump(agent_data, f)

        # Create message log with different message types
        log_file = tmp_path / "agent_messages.log"
        message_types = ["INFO", "QUESTION", "BLOCKED"]
        with open(log_file, "w") as f:
            for msg_type in message_types:
                msg = {
                    "sender": "agent-other",
                    "timestamp": datetime.now().isoformat(),
                    "msg_type": msg_type,
                    "content": f"{msg_type} message",
                    "recipients": ["agent-1"],
                    "msg_id": f"msg-{msg_type}",
                }
                f.write(json.dumps(msg) + "\n")

        with patch("claudeswarm.messaging.get_messages_log_path", return_value=log_file):
            args = argparse.Namespace()

            with pytest.raises(SystemExit):
                cmd_whoami(args)

            captured = capsys.readouterr()

            # Verify all message types are displayed
            for msg_type in message_types:
                assert msg_type in captured.out
                assert f"{msg_type} message" in captured.out

        if "TMUX_PANE" in os.environ:
            del os.environ["TMUX_PANE"]


class TestWhoamiMessageIntegration:
    """Integration tests for whoami message display."""

    def test_message_logger_integration_with_whoami(self, tmp_path):
        """Test MessageLogger integration with whoami command."""
        # Create a message logger
        log_file = tmp_path / "agent_messages.log"
        logger = MessageLogger(log_file)

        # Log some messages
        for i in range(5):
            msg = Message(
                sender_id=f"agent-{i}",
                timestamp=datetime.now(),
                msg_type=MessageType.INFO,
                content=f"Integration test message {i}",
                recipients=["agent-target"],
            )
            logger.log_message(msg, {"agent-target": True})

        # Get messages (simulating what whoami does)
        messages = logger.get_messages_for_agent("agent-target", limit=3)

        # Verify we get the 3 most recent
        assert len(messages) == 3
        assert "Integration test message 2" in messages[0]["content"]
        assert "Integration test message 3" in messages[1]["content"]
        assert "Integration test message 4" in messages[2]["content"]

    def test_whoami_constant_matches_implementation(self):
        """Test that WHOAMI_MESSAGE_PREVIEW_LIMIT constant is used correctly."""
        # This test verifies that the constant value matches what's used in the code
        assert WHOAMI_MESSAGE_PREVIEW_LIMIT == 3, "WHOAMI_MESSAGE_PREVIEW_LIMIT should be 3"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
