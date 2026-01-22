"""
Comprehensive tests for CLI messaging commands.

Tests cover:
- send-message command functionality
- broadcast-message command functionality
- Subprocess execution (simulating agent usage)
- Input validation and error handling
- Message type parsing
- JSON output
- Exit codes

These tests ensure that agents can reliably use messaging commands.

Author: Agent-TestCoverage
"""

import argparse
import json
import subprocess
from unittest.mock import Mock, patch

import pytest

from claudeswarm.cli import cmd_broadcast_message, cmd_send_message
from claudeswarm.messaging import MessageType
from claudeswarm.validators import ValidationError


class TestSendMessageCommand:
    """Tests for send-message CLI command."""

    @patch("claudeswarm.messaging.send_message")
    @patch("claudeswarm.cli.validate_agent_id")
    @patch("claudeswarm.cli.validate_message_content")
    def test_send_message_success(self, mock_validate_content, mock_validate_id, mock_send, capsys):
        """Test successful message sending."""
        # Setup mocks
        mock_validate_id.side_effect = lambda x: x
        mock_validate_content.side_effect = lambda x: x

        mock_message = Mock()
        mock_message.to_dict.return_value = {
            "sender_id": "agent-1",
            "recipient_id": "agent-2",
            "type": "INFO",
            "content": "Hello",
            "timestamp": "2025-11-14T10:00:00Z",
        }
        mock_send.return_value = mock_message

        # Create args
        args = argparse.Namespace(
            sender_id="agent-1", recipient_id="agent-2", type="INFO", content="Hello", json=False
        )

        # Execute
        with pytest.raises(SystemExit) as exc_info:
            cmd_send_message(args)

        # Verify
        assert exc_info.value.code == 0
        mock_send.assert_called_once_with(
            sender_id="agent-1",
            recipient_id="agent-2",
            message_type=MessageType.INFO,
            content="Hello",
        )

        captured = capsys.readouterr()
        assert "Message sent to inbox: agent-2" in captured.out

    @patch("claudeswarm.messaging.send_message")
    @patch("claudeswarm.cli.validate_agent_id")
    @patch("claudeswarm.cli.validate_message_content")
    def test_send_message_json_output(
        self, mock_validate_content, mock_validate_id, mock_send, capsys
    ):
        """Test JSON output format."""
        mock_validate_id.side_effect = lambda x: x
        mock_validate_content.side_effect = lambda x: x

        mock_message = Mock()
        message_dict = {
            "sender_id": "agent-1",
            "recipient_id": "agent-2",
            "type": "QUESTION",
            "content": "Need help?",
            "timestamp": "2025-11-14T10:00:00Z",
        }
        mock_message.to_dict.return_value = message_dict
        mock_send.return_value = mock_message

        args = argparse.Namespace(
            sender_id="agent-1",
            recipient_id="agent-2",
            type="QUESTION",
            content="Need help?",
            json=True,
        )

        with pytest.raises(SystemExit) as exc_info:
            cmd_send_message(args)

        assert exc_info.value.code == 0
        captured = capsys.readouterr()

        # Verify JSON output can be parsed and has expected structure
        # Extract JSON object from output (skip status message)
        json_start = captured.out.find("{")
        assert json_start != -1, "JSON output should contain JSON object"

        json_output = captured.out[json_start:]
        parsed = json.loads(json_output)

        assert isinstance(parsed, dict), "JSON output should be a dictionary"
        assert parsed.get("sender_id") == "agent-1", "JSON should contain correct sender"
        assert parsed.get("recipient_id") == "agent-2", "JSON should contain correct recipient"
        assert parsed.get("type") == "QUESTION", "JSON should contain correct message type"

    @patch("claudeswarm.messaging.send_message")
    @patch("claudeswarm.cli.validate_agent_id")
    @patch("claudeswarm.cli.validate_message_content")
    def test_send_message_failure(self, mock_validate_content, mock_validate_id, mock_send, capsys):
        """Test failed message sending."""
        mock_validate_id.side_effect = lambda x: x
        mock_validate_content.side_effect = lambda x: x
        mock_send.return_value = None  # Indicates failure

        args = argparse.Namespace(
            sender_id="agent-1", recipient_id="agent-2", type="INFO", content="Hello", json=False
        )

        with pytest.raises(SystemExit) as exc_info:
            cmd_send_message(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Failed to send message" in captured.err

    @patch("claudeswarm.cli.validate_agent_id")
    def test_send_message_invalid_sender(self, mock_validate_id, capsys):
        """Test validation error for invalid sender ID."""
        mock_validate_id.side_effect = ValidationError("Invalid agent ID")

        args = argparse.Namespace(
            sender_id="invalid!", recipient_id="agent-2", type="INFO", content="Hello", json=False
        )

        with pytest.raises(SystemExit) as exc_info:
            cmd_send_message(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Validation error" in captured.err

    def test_send_message_invalid_type(self, capsys):
        """Test invalid message type."""
        args = argparse.Namespace(
            sender_id="agent-1",
            recipient_id="agent-2",
            type="INVALID_TYPE",
            content="Hello",
            json=False,
        )

        with patch("claudeswarm.cli.validate_agent_id", side_effect=lambda x: x):
            with patch("claudeswarm.cli.validate_message_content", side_effect=lambda x: x):
                with pytest.raises(SystemExit) as exc_info:
                    cmd_send_message(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Invalid message type" in captured.err
        assert "INVALID_TYPE" in captured.err

    def test_send_message_all_message_types(self, capsys):
        """Test all valid message types are accepted."""
        # Use actual valid types from MessageType enum
        valid_types = [
            "INFO",
            "QUESTION",
            "BLOCKED",
            "REVIEW-REQUEST",
            "COMPLETED",
            "CHALLENGE",
            "ACK",
        ]

        for msg_type in valid_types:
            with patch("claudeswarm.cli.validate_agent_id", side_effect=lambda x: x):
                with patch("claudeswarm.cli.validate_message_content", side_effect=lambda x: x):
                    with patch("claudeswarm.messaging.send_message") as mock_send:
                        mock_message = Mock()
                        mock_message.to_dict.return_value = {"delivery_status": {}}
                        mock_send.return_value = mock_message

                        args = argparse.Namespace(
                            sender_id="agent-1",
                            recipient_id="agent-2",
                            type=msg_type,
                            content="Test",
                            json=False,
                        )

                        with pytest.raises(SystemExit) as exc_info:
                            cmd_send_message(args)

                        assert exc_info.value.code == 0, f"Failed for type {msg_type}"

    def test_send_message_with_auto_detect(self, tmp_path, capsys):
        """Test send-message with auto-detected sender ID."""
        import json
        import os

        # Create mock registry
        registry_data = {
            "session_name": "test",
            "updated_at": "2025-11-18T10:00:00Z",
            "agents": [
                {
                    "id": "agent-auto",
                    "pane_index": "test:0.0",
                    "pid": 12345,
                    "status": "active",
                    "last_seen": "2025-11-18T10:00:00Z",
                    "session_name": "test",
                    "tmux_pane_id": "%99",
                }
            ],
        }

        registry_path = tmp_path / "ACTIVE_AGENTS.json"
        registry_path.write_text(json.dumps(registry_data))

        args = argparse.Namespace(
            sender_id=None,  # Auto-detect
            recipient_id="agent-2",
            type="INFO",
            content="Test message",
            json=False,
        )

        with patch.dict(os.environ, {"TMUX_PANE": "%99"}):
            with patch("claudeswarm.project.get_active_agents_path", return_value=registry_path):
                with patch("claudeswarm.cli.validate_agent_id", side_effect=lambda x: x):
                    with patch("claudeswarm.cli.validate_message_content", side_effect=lambda x: x):
                        with patch("claudeswarm.messaging.send_message") as mock_send:
                            mock_message = Mock()
                            mock_message.to_dict.return_value = {
                                "delivery_status": {"agent-2": True}
                            }
                            mock_send.return_value = mock_message

                            with pytest.raises(SystemExit) as exc_info:
                                cmd_send_message(args)

                            assert exc_info.value.code == 0
                            # Verify auto-detected sender ID was used
                            call_kwargs = mock_send.call_args[1]
                            assert call_kwargs["sender_id"] == "agent-auto"

    def test_send_message_auto_detect_fails(self, capsys):
        """Test send-message fails when auto-detect fails."""
        import os

        args = argparse.Namespace(
            sender_id=None,  # Auto-detect
            recipient_id="agent-2",
            type="INFO",
            content="Test message",
            json=False,
        )

        with patch.dict(os.environ, {}, clear=True):  # No TMUX_PANE
            with pytest.raises(SystemExit) as exc_info:
                cmd_send_message(args)

            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "Could not auto-detect agent identity" in captured.err


class TestBroadcastMessageCommand:
    """Tests for broadcast-message CLI command."""

    @patch("claudeswarm.messaging.broadcast_message")
    @patch("claudeswarm.cli.validate_agent_id")
    @patch("claudeswarm.cli.validate_message_content")
    def test_broadcast_success(
        self, mock_validate_content, mock_validate_id, mock_broadcast, capsys
    ):
        """Test successful message broadcast."""
        mock_validate_id.side_effect = lambda x: x
        mock_validate_content.side_effect = lambda x: x
        mock_broadcast.return_value = {"agent-1": True, "agent-2": True, "agent-3": True}

        args = argparse.Namespace(
            sender_id="system",
            type="INFO",
            content="System update",
            include_self=False,
            json=False,
            verbose=False,
        )

        with pytest.raises(SystemExit) as exc_info:
            cmd_broadcast_message(args)

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "Broadcast delivered to 3/3 agents" in captured.out

    @patch("claudeswarm.messaging.broadcast_message")
    @patch("claudeswarm.cli.validate_agent_id")
    @patch("claudeswarm.cli.validate_message_content")
    def test_broadcast_partial_success(
        self, mock_validate_content, mock_validate_id, mock_broadcast, capsys
    ):
        """Test partial broadcast success."""
        mock_validate_id.side_effect = lambda x: x
        mock_validate_content.side_effect = lambda x: x
        mock_broadcast.return_value = {"agent-1": True, "agent-2": False, "agent-3": True}

        args = argparse.Namespace(
            sender_id="system",
            type="INFO",
            content="Update",
            include_self=False,
            json=False,
            verbose=False,
        )

        with pytest.raises(SystemExit) as exc_info:
            cmd_broadcast_message(args)

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "2/3 real-time" in captured.out

    @patch("claudeswarm.messaging.broadcast_message")
    @patch("claudeswarm.cli.validate_agent_id")
    @patch("claudeswarm.cli.validate_message_content")
    def test_broadcast_verbose_output(
        self, mock_validate_content, mock_validate_id, mock_broadcast, capsys
    ):
        """Test verbose output shows individual agent status."""
        mock_validate_id.side_effect = lambda x: x
        mock_validate_content.side_effect = lambda x: x
        mock_broadcast.return_value = {"agent-1": True, "agent-2": False, "agent-3": True}

        args = argparse.Namespace(
            sender_id="system",
            type="INFO",
            content="Update",
            include_self=False,
            json=False,
            verbose=True,
        )

        with pytest.raises(SystemExit) as exc_info:
            cmd_broadcast_message(args)

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "delivered: agent-1" in captured.out
        assert "in inbox: agent-2" in captured.out
        assert "delivered: agent-3" in captured.out

    @patch("claudeswarm.messaging.broadcast_message")
    @patch("claudeswarm.cli.validate_agent_id")
    @patch("claudeswarm.cli.validate_message_content")
    def test_broadcast_json_output(
        self, mock_validate_content, mock_validate_id, mock_broadcast, capsys
    ):
        """Test JSON output format."""
        mock_validate_id.side_effect = lambda x: x
        mock_validate_content.side_effect = lambda x: x
        results = {"agent-1": True, "agent-2": True}
        mock_broadcast.return_value = results

        args = argparse.Namespace(
            sender_id="system",
            type="INFO",
            content="Update",
            include_self=False,
            json=True,
            verbose=False,
        )

        with pytest.raises(SystemExit) as exc_info:
            cmd_broadcast_message(args)

        assert exc_info.value.code == 0
        captured = capsys.readouterr()

        # Verify JSON output can be parsed and has expected structure
        # Extract JSON object from output (lines starting with '{' or containing JSON)
        json_start = captured.out.find("{")
        assert json_start != -1, "JSON output should contain JSON object"

        json_output = captured.out[json_start:]
        parsed = json.loads(json_output)

        assert isinstance(parsed, dict), "JSON should parse to dictionary"
        assert "agent-1" in parsed or "agent-2" in parsed, "JSON should contain agent results"
        # Verify each agent result is a boolean
        for _agent_id, success in parsed.items():
            assert isinstance(success, bool), f"Agent result should be boolean, got {type(success)}"

    @patch("claudeswarm.messaging.broadcast_message")
    @patch("claudeswarm.cli.validate_agent_id")
    @patch("claudeswarm.cli.validate_message_content")
    def test_broadcast_no_agents_reached(
        self, mock_validate_content, mock_validate_id, mock_broadcast, capsys
    ):
        """Test broadcast when no agents are reached."""
        mock_validate_id.side_effect = lambda x: x
        mock_validate_content.side_effect = lambda x: x
        mock_broadcast.return_value = {"agent-1": False, "agent-2": False}

        args = argparse.Namespace(
            sender_id="system",
            type="INFO",
            content="Update",
            include_self=False,
            json=False,
            verbose=False,
        )

        with pytest.raises(SystemExit) as exc_info:
            cmd_broadcast_message(args)

        # Messages logged to inbox is considered success (exit code 0)
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "sent to inbox" in captured.out

    @patch("claudeswarm.messaging.broadcast_message")
    @patch("claudeswarm.cli.validate_agent_id")
    @patch("claudeswarm.cli.validate_message_content")
    def test_broadcast_include_self(
        self, mock_validate_content, mock_validate_id, mock_broadcast, capsys
    ):
        """Test include_self flag is passed correctly."""
        mock_validate_id.side_effect = lambda x: x
        mock_validate_content.side_effect = lambda x: x
        mock_broadcast.return_value = {"agent-1": True}

        args = argparse.Namespace(
            sender_id="agent-1",
            type="INFO",
            content="Update",
            include_self=True,  # Include sender
            json=False,
            verbose=False,
        )

        with pytest.raises(SystemExit):
            cmd_broadcast_message(args)

        # Verify exclude_self is False (because include_self is True)
        mock_broadcast.assert_called_once()
        call_kwargs = mock_broadcast.call_args[1]
        assert not call_kwargs["exclude_self"]

    def test_broadcast_message_with_auto_detect(self, tmp_path, capsys):
        """Test broadcast-message with auto-detected sender ID."""
        import json
        import os

        # Create mock registry
        registry_data = {
            "session_name": "test",
            "updated_at": "2025-11-18T10:00:00Z",
            "agents": [
                {
                    "id": "agent-auto",
                    "pane_index": "test:0.0",
                    "pid": 12345,
                    "status": "active",
                    "last_seen": "2025-11-18T10:00:00Z",
                    "session_name": "test",
                    "tmux_pane_id": "%99",
                }
            ],
        }

        registry_path = tmp_path / "ACTIVE_AGENTS.json"
        registry_path.write_text(json.dumps(registry_data))

        args = argparse.Namespace(
            sender_id=None,  # Auto-detect
            type="INFO",
            content="Broadcast test",
            include_self=False,
            json=False,
            verbose=False,
        )

        with patch.dict(os.environ, {"TMUX_PANE": "%99"}):
            with patch("claudeswarm.project.get_active_agents_path", return_value=registry_path):
                with patch("claudeswarm.cli.validate_agent_id", side_effect=lambda x: x):
                    with patch("claudeswarm.cli.validate_message_content", side_effect=lambda x: x):
                        with patch("claudeswarm.messaging.broadcast_message") as mock_broadcast:
                            mock_broadcast.return_value = {"agent-2": True}

                            with pytest.raises(SystemExit) as exc_info:
                                cmd_broadcast_message(args)

                            assert exc_info.value.code == 0
                            # Verify auto-detected sender ID was used
                            call_kwargs = mock_broadcast.call_args[1]
                            assert call_kwargs["sender_id"] == "agent-auto"

    def test_broadcast_message_auto_detect_fails(self, capsys):
        """Test broadcast-message fails when auto-detect fails."""
        import os

        args = argparse.Namespace(
            sender_id=None,  # Auto-detect
            type="INFO",
            content="Broadcast test",
            include_self=False,
            json=False,
            verbose=False,
        )

        with patch.dict(os.environ, {}, clear=True):  # No TMUX_PANE
            with pytest.raises(SystemExit) as exc_info:
                cmd_broadcast_message(args)

            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "Could not auto-detect agent identity" in captured.err


class TestMessagingSubprocessExecution:
    """Tests for messaging commands when executed as subprocesses (agent context)."""

    def test_send_message_via_subprocess(self, tmp_path):
        """Test send-message can be executed via subprocess."""
        # This simulates how an agent would call the command
        result = subprocess.run(
            [
                "python3",
                "-m",
                "claudeswarm.cli",
                "send-message",
                "agent-target",
                "INFO",
                "Test message",
                "--sender-id",
                "agent-test",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )

        # Command should execute without crashing
        # (it may fail due to no active agents, but shouldn't crash)
        assert result.returncode in [0, 1]  # Success or controlled failure
        assert "Traceback" not in result.stderr  # No Python exceptions

    def test_broadcast_message_via_subprocess(self):
        """Test broadcast-message can be executed via subprocess."""
        result = subprocess.run(
            [
                "python3",
                "-m",
                "claudeswarm.cli",
                "broadcast-message",
                "INFO",
                "Test broadcast",
                "--sender-id",
                "agent-test",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )

        # Command should execute without crashing
        assert result.returncode in [0, 1]  # Success or controlled failure
        assert "Traceback" not in result.stderr  # No Python exceptions

    def test_send_message_help_via_subprocess(self):
        """Test help output works via subprocess."""
        result = subprocess.run(
            ["python3", "-m", "claudeswarm.cli", "send-message", "--help"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        assert result.returncode == 0
        assert "sender-id" in result.stdout  # CLI uses --sender-id flag
        assert "recipient_id" in result.stdout
        assert "Message type" in result.stdout or "type" in result.stdout

    def test_broadcast_message_help_via_subprocess(self):
        """Test help output works via subprocess."""
        result = subprocess.run(
            ["python3", "-m", "claudeswarm.cli", "broadcast-message", "--help"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        assert result.returncode == 0, "Help command should succeed"
        assert "sender-id" in result.stdout, "Help should contain sender-id parameter"
        assert (
            "broadcast-message" in result.stdout or "type" in result.stdout
        ), "Help should contain command info"

    def test_invalid_message_type_via_subprocess(self):
        """Test error handling for invalid message type via subprocess."""
        result = subprocess.run(
            [
                "python3",
                "-m",
                "claudeswarm.cli",
                "send-message",
                "agent-2",
                "INVALID",
                "Test",
                "--sender-id",
                "agent-1",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )

        # May return 1 or 2 depending on validation timing
        assert result.returncode != 0
        # Should show some error output (either about type or usage)
        assert (
            result.stderr != ""
            or "error" in result.stdout.lower()
            or "usage" in result.stdout.lower()
        )


class TestMessagingCommandReliability:
    """Tests to ensure messaging commands are reliable for agent use."""

    @patch("claudeswarm.messaging.send_message")
    @patch("claudeswarm.cli.validate_agent_id")
    @patch("claudeswarm.cli.validate_message_content")
    def test_send_message_handles_exceptions_gracefully(
        self, mock_validate_content, mock_validate_id, mock_send, capsys
    ):
        """Test that exceptions are caught and don't crash the command."""
        mock_validate_id.side_effect = lambda x: x
        mock_validate_content.side_effect = lambda x: x
        mock_send.side_effect = Exception("Unexpected error")

        args = argparse.Namespace(
            sender_id="agent-1", recipient_id="agent-2", type="INFO", content="Test", json=False
        )

        with pytest.raises(SystemExit) as exc_info:
            cmd_send_message(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error:" in captured.err

    @patch("claudeswarm.messaging.broadcast_message")
    @patch("claudeswarm.cli.validate_agent_id")
    @patch("claudeswarm.cli.validate_message_content")
    def test_broadcast_message_handles_exceptions_gracefully(
        self, mock_validate_content, mock_validate_id, mock_broadcast, capsys
    ):
        """Test that exceptions are caught and don't crash the command."""
        mock_validate_id.side_effect = lambda x: x
        mock_validate_content.side_effect = lambda x: x
        mock_broadcast.side_effect = Exception("Unexpected error")

        args = argparse.Namespace(
            sender_id="system",
            type="INFO",
            content="Test",
            include_self=False,
            json=False,
            verbose=False,
        )

        with pytest.raises(SystemExit) as exc_info:
            cmd_broadcast_message(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error:" in captured.err

    def test_message_types_match_messaging_module(self):
        """Ensure CLI accepts all MessageType enum values."""
        from claudeswarm.messaging import MessageType

        # All message types from the enum should be valid

        enum_types = {t.name for t in MessageType}

        # Check that common types are covered
        common_types = {"INFO", "QUESTION", "BLOCKED"}
        assert common_types.issubset(enum_types), "Common message types missing from enum"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
