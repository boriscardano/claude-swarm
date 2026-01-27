"""
Comprehensive tests for CLI auto-detection functionality.

Tests cover:
- _detect_current_agent() function with various scenarios
- Valid tmux_pane_id scenarios
- Missing TMUX_PANE environment variable
- Missing/corrupt registry file
- Fallback to pane_index and PID
- Tmux subprocess failures
- Integration with lock and messaging commands

Author: Agent-TestCoverage
"""

import argparse
import json
import os
import subprocess
from pathlib import Path
from contextlib import contextmanager


@contextmanager
def mock_pid_alive():
    """Context manager to mock os.kill to simulate that test PIDs are alive."""
    from unittest.mock import patch

    with patch("os.kill") as mock_kill:
        mock_kill.return_value = None  # Simulate process exists
        yield mock_kill
from unittest.mock import Mock, patch

import pytest

from claudeswarm.cli import (
    _detect_current_agent,
    cmd_acquire_file_lock,
    cmd_broadcast_message,
    cmd_release_file_lock,
    cmd_send_message,
)


class TestDetectCurrentAgent:
    """Tests for _detect_current_agent() function."""

    def test_detect_by_tmux_pane_id_success(self, tmp_path):
        """Test successful detection via TMUX_PANE environment variable."""
        # Setup mock registry
        registry_data = {
            "session_name": "test-session",
            "updated_at": "2025-11-18T10:00:00Z",
            "agents": [
                {
                    "id": "agent-1",
                    "pane_index": "test:0.0",
                    "pid": 12345,
                    "status": "active",
                    "last_seen": "2025-11-18T10:00:00Z",
                    "session_name": "test-session",
                    "tmux_pane_id": "%2",
                },
                {
                    "id": "agent-2",
                    "pane_index": "test:0.1",
                    "pid": 12346,
                    "status": "active",
                    "last_seen": "2025-11-18T10:00:00Z",
                    "session_name": "test-session",
                    "tmux_pane_id": "%3",
                },
            ],
        }

        # Create registry file
        registry_path = tmp_path / "ACTIVE_AGENTS.json"
        registry_path.write_text(json.dumps(registry_data))

        # Mock environment, path, and os.kill to simulate that the agent's PID is alive
        with patch.dict(os.environ, {"TMUX_PANE": "%2"}):
            with patch("claudeswarm.project.get_active_agents_path", return_value=registry_path):
                with patch("os.kill") as mock_kill:
                    mock_kill.return_value = None  # Simulate process exists
                    agent_id, agent_dict = _detect_current_agent()

        assert agent_id == "agent-1"
        assert agent_dict is not None
        assert agent_dict["id"] == "agent-1"
        assert agent_dict["tmux_pane_id"] == "%2"

    def test_detect_missing_tmux_pane_env(self):
        """Test detection fails when TMUX_PANE is not set."""
        with patch.dict(os.environ, {}, clear=True):
            agent_id, agent_dict = _detect_current_agent()

        assert agent_id is None
        assert agent_dict is None

    def test_detect_missing_registry_file(self, tmp_path):
        """Test detection fails when registry file doesn't exist."""
        nonexistent_path = tmp_path / "nonexistent" / "ACTIVE_AGENTS.json"

        with patch.dict(os.environ, {"TMUX_PANE": "%2"}):
            with patch("claudeswarm.project.get_active_agents_path", return_value=nonexistent_path):
                agent_id, agent_dict = _detect_current_agent()

        assert agent_id is None
        assert agent_dict is None

    def test_detect_corrupt_registry_file(self, tmp_path):
        """Test detection fails gracefully with corrupt JSON."""
        registry_path = tmp_path / "ACTIVE_AGENTS.json"
        registry_path.write_text("{ invalid json }")

        with patch.dict(os.environ, {"TMUX_PANE": "%2"}):
            with patch("claudeswarm.project.get_active_agents_path", return_value=registry_path):
                agent_id, agent_dict = _detect_current_agent()

        assert agent_id is None
        assert agent_dict is None

    def test_detect_fallback_to_pane_index(self, tmp_path):
        """Test fallback to pane_index when tmux_pane_id match fails."""
        registry_data = {
            "session_name": "test-session",
            "updated_at": "2025-11-18T10:00:00Z",
            "agents": [
                {
                    "id": "agent-1",
                    "pane_index": "test:0.0",
                    "pid": 12345,
                    "status": "active",
                    "last_seen": "2025-11-18T10:00:00Z",
                    "session_name": "test-session",
                    "tmux_pane_id": "%99",  # Different pane ID
                }
            ],
        }

        registry_path = tmp_path / "ACTIVE_AGENTS.json"
        registry_path.write_text(json.dumps(registry_data))

        # Mock subprocess to return pane index
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "test:0.0\n"

        with patch.dict(os.environ, {"TMUX_PANE": "%2"}):
            with patch("claudeswarm.project.get_active_agents_path", return_value=registry_path):
                with patch("subprocess.run", return_value=mock_result):
                    agent_id, agent_dict = _detect_current_agent()

        assert agent_id == "agent-1"
        assert agent_dict["pane_index"] == "test:0.0"

    def test_detect_tmux_subprocess_failure(self, tmp_path):
        """Test handling of tmux subprocess failures."""
        registry_data = {
            "session_name": "test-session",
            "updated_at": "2025-11-18T10:00:00Z",
            "agents": [
                {
                    "id": "agent-1",
                    "pane_index": "test:0.0",
                    "pid": 12345,
                    "status": "active",
                    "last_seen": "2025-11-18T10:00:00Z",
                    "session_name": "test-session",
                }
            ],
        }

        registry_path = tmp_path / "ACTIVE_AGENTS.json"
        registry_path.write_text(json.dumps(registry_data))

        # Mock subprocess to fail
        with patch.dict(os.environ, {"TMUX_PANE": "%2"}):
            with patch("claudeswarm.project.get_active_agents_path", return_value=registry_path):
                with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(["tmux"], 2.0)):
                    agent_id, agent_dict = _detect_current_agent()

        # Should return None when tmux fails and no tmux_pane_id match
        assert agent_id is None
        assert agent_dict is None

    def test_detect_tmux_not_found(self, tmp_path):
        """Test handling when tmux binary is not found."""
        registry_data = {
            "session_name": "test-session",
            "updated_at": "2025-11-18T10:00:00Z",
            "agents": [],
        }

        registry_path = tmp_path / "ACTIVE_AGENTS.json"
        registry_path.write_text(json.dumps(registry_data))

        with patch.dict(os.environ, {"TMUX_PANE": "%2"}):
            with patch("claudeswarm.project.get_active_agents_path", return_value=registry_path):
                with patch("subprocess.run", side_effect=FileNotFoundError()):
                    agent_id, agent_dict = _detect_current_agent()

        assert agent_id is None
        assert agent_dict is None

    def test_detect_agent_without_tmux_pane_id(self, tmp_path):
        """Test detection with old registry format (no tmux_pane_id field)."""
        registry_data = {
            "session_name": "test-session",
            "updated_at": "2025-11-18T10:00:00Z",
            "agents": [
                {
                    "id": "agent-1",
                    "pane_index": "test:0.0",
                    "pid": 12345,
                    "status": "active",
                    "last_seen": "2025-11-18T10:00:00Z",
                    "session_name": "test-session",
                    # No tmux_pane_id field
                }
            ],
        }

        registry_path = tmp_path / "ACTIVE_AGENTS.json"
        registry_path.write_text(json.dumps(registry_data))

        # Mock subprocess to return pane index
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "test:0.0\n"

        with patch.dict(os.environ, {"TMUX_PANE": "%2"}):
            with patch("claudeswarm.project.get_active_agents_path", return_value=registry_path):
                with patch("subprocess.run", return_value=mock_result):
                    agent_id, agent_dict = _detect_current_agent()

        assert agent_id == "agent-1"

    def test_detect_multiple_agents_correct_match(self, tmp_path):
        """Test correct agent is returned when multiple agents exist."""
        registry_data = {
            "session_name": "test-session",
            "updated_at": "2025-11-18T10:00:00Z",
            "agents": [
                {
                    "id": "agent-1",
                    "pane_index": "test:0.0",
                    "pid": 12345,
                    "status": "active",
                    "last_seen": "2025-11-18T10:00:00Z",
                    "session_name": "test-session",
                    "tmux_pane_id": "%2",
                },
                {
                    "id": "agent-2",
                    "pane_index": "test:0.1",
                    "pid": 12346,
                    "status": "active",
                    "last_seen": "2025-11-18T10:00:00Z",
                    "session_name": "test-session",
                    "tmux_pane_id": "%3",
                },
                {
                    "id": "agent-3",
                    "pane_index": "test:0.2",
                    "pid": 12347,
                    "status": "active",
                    "last_seen": "2025-11-18T10:00:00Z",
                    "session_name": "test-session",
                    "tmux_pane_id": "%4",
                },
            ],
        }

        registry_path = tmp_path / "ACTIVE_AGENTS.json"
        registry_path.write_text(json.dumps(registry_data))

        with patch.dict(os.environ, {"TMUX_PANE": "%3"}):
            with patch("claudeswarm.project.get_active_agents_path", return_value=registry_path):
                with mock_pid_alive():
                    agent_id, agent_dict = _detect_current_agent()

        assert agent_id == "agent-2"
        assert agent_dict["tmux_pane_id"] == "%3"

    def test_detect_empty_agents_list(self, tmp_path):
        """Test detection with empty agents list."""
        registry_data = {
            "session_name": "test-session",
            "updated_at": "2025-11-18T10:00:00Z",
            "agents": [],
        }

        registry_path = tmp_path / "ACTIVE_AGENTS.json"
        registry_path.write_text(json.dumps(registry_data))

        with patch.dict(os.environ, {"TMUX_PANE": "%2"}):
            with patch("claudeswarm.project.get_active_agents_path", return_value=registry_path):
                agent_id, agent_dict = _detect_current_agent()

        assert agent_id is None
        assert agent_dict is None


class TestAutoDetectInLockCommands:
    """Tests for auto-detection in lock commands."""

    def test_acquire_lock_auto_detect_success(self, tmp_path, capsys):
        """Test acquire-file-lock with successful auto-detection."""
        registry_data = {
            "session_name": "test",
            "updated_at": "2025-11-18T10:00:00Z",
            "agents": [
                {
                    "id": "agent-1",
                    "pane_index": "test:0.0",
                    "pid": 12345,
                    "status": "active",
                    "last_seen": "2025-11-18T10:00:00Z",
                    "session_name": "test",
                    "tmux_pane_id": "%2",
                }
            ],
        }

        registry_path = tmp_path / "ACTIVE_AGENTS.json"
        registry_path.write_text(json.dumps(registry_data))

        args = argparse.Namespace(
            project_root=tmp_path,
            filepath="test.txt",
            agent_id=None,  # No agent ID provided
            reason="testing",
        )

        with patch.dict(os.environ, {"TMUX_PANE": "%2"}):
            with patch("claudeswarm.project.get_active_agents_path", return_value=registry_path):
                with mock_pid_alive():
                    with patch("claudeswarm.cli.LockManager") as mock_manager_class:
                        mock_manager = Mock()
                        mock_manager.acquire_lock.return_value = (True, None)
                        mock_manager_class.return_value = mock_manager

                        with pytest.raises(SystemExit) as exc_info:
                            cmd_acquire_file_lock(args)

                        assert exc_info.value.code == 0
                        # Verify the call used auto-detected agent ID
                        mock_manager.acquire_lock.assert_called_once()
                        call_kwargs = mock_manager.acquire_lock.call_args[1]
                        assert call_kwargs["agent_id"] == "agent-1"

    def test_acquire_lock_auto_detect_failure(self, capsys):
        """Test acquire-file-lock fails when auto-detection fails."""
        args = argparse.Namespace(
            project_root=Path("/test"),
            filepath="test.txt",
            agent_id=None,  # No agent ID provided
            reason="testing",
        )

        with patch.dict(os.environ, {}, clear=True):  # No TMUX_PANE
            with pytest.raises(SystemExit) as exc_info:
                cmd_acquire_file_lock(args)

            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "Could not auto-detect agent identity" in captured.err

    def test_release_lock_auto_detect_success(self, tmp_path, capsys):
        """Test release-file-lock with successful auto-detection."""
        registry_data = {
            "session_name": "test",
            "updated_at": "2025-11-18T10:00:00Z",
            "agents": [
                {
                    "id": "agent-1",
                    "pane_index": "test:0.0",
                    "pid": 12345,
                    "status": "active",
                    "last_seen": "2025-11-18T10:00:00Z",
                    "session_name": "test",
                    "tmux_pane_id": "%2",
                }
            ],
        }

        registry_path = tmp_path / "ACTIVE_AGENTS.json"
        registry_path.write_text(json.dumps(registry_data))

        args = argparse.Namespace(
            project_root=tmp_path, filepath="test.txt", agent_id=None  # No agent ID provided
        )

        with patch.dict(os.environ, {"TMUX_PANE": "%2"}):
            with patch("claudeswarm.project.get_active_agents_path", return_value=registry_path):
                with mock_pid_alive():
                    with patch("claudeswarm.cli.LockManager") as mock_manager_class:
                        mock_manager = Mock()
                        mock_manager.release_lock.return_value = True
                        mock_manager_class.return_value = mock_manager

                        with pytest.raises(SystemExit) as exc_info:
                            cmd_release_file_lock(args)

                        assert exc_info.value.code == 0
                        # Verify the call used auto-detected agent ID
                        mock_manager.release_lock.assert_called_once()
                        call_kwargs = mock_manager.release_lock.call_args[1]
                        assert call_kwargs["agent_id"] == "agent-1"

    def test_release_lock_auto_detect_failure(self, capsys):
        """Test release-file-lock fails when auto-detection fails."""
        args = argparse.Namespace(
            project_root=Path("/test"), filepath="test.txt", agent_id=None  # No agent ID provided
        )

        with patch.dict(os.environ, {}, clear=True):  # No TMUX_PANE
            with pytest.raises(SystemExit) as exc_info:
                cmd_release_file_lock(args)

            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "Could not auto-detect agent identity" in captured.err

    def test_acquire_lock_explicit_agent_id(self, capsys):
        """Test acquire-file-lock with explicit agent ID (no auto-detection)."""
        args = argparse.Namespace(
            project_root=Path("/test"),
            filepath="test.txt",
            agent_id="agent-explicit",  # Explicit agent ID
            reason="testing",
        )

        with patch("claudeswarm.cli.LockManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager.acquire_lock.return_value = (True, None)
            mock_manager_class.return_value = mock_manager

            with pytest.raises(SystemExit) as exc_info:
                cmd_acquire_file_lock(args)

            assert exc_info.value.code == 0
            # Verify the call used explicit agent ID
            call_kwargs = mock_manager.acquire_lock.call_args[1]
            assert call_kwargs["agent_id"] == "agent-explicit"


class TestAutoDetectInMessagingCommands:
    """Tests for auto-detection in messaging commands."""

    def test_send_message_auto_detect_success(self, tmp_path, capsys):
        """Test send-message with successful auto-detection."""
        registry_data = {
            "session_name": "test",
            "updated_at": "2025-11-18T10:00:00Z",
            "agents": [
                {
                    "id": "agent-1",
                    "pane_index": "test:0.0",
                    "pid": 12345,
                    "status": "active",
                    "last_seen": "2025-11-18T10:00:00Z",
                    "session_name": "test",
                    "tmux_pane_id": "%2",
                }
            ],
        }

        registry_path = tmp_path / "ACTIVE_AGENTS.json"
        registry_path.write_text(json.dumps(registry_data))

        args = argparse.Namespace(
            sender_id=None,  # No sender ID provided
            recipient_id="agent-2",
            type="INFO",
            content="Test message",
            json=False,
        )

        with patch.dict(os.environ, {"TMUX_PANE": "%2"}):
            with patch("claudeswarm.project.get_active_agents_path", return_value=registry_path):
                with mock_pid_alive():
                    with patch("claudeswarm.cli.validate_agent_id", side_effect=lambda x: x):
                        with patch("claudeswarm.cli.validate_message_content", side_effect=lambda x: x):
                            with patch("claudeswarm.messaging.send_message") as mock_send:
                                mock_msg = Mock()
                                mock_msg.to_dict.return_value = {"delivery_status": {"agent-2": True}}
                                mock_send.return_value = mock_msg

                                with pytest.raises(SystemExit) as exc_info:
                                    cmd_send_message(args)

                                assert exc_info.value.code == 0
                                # Verify the call used auto-detected sender ID
                                call_kwargs = mock_send.call_args[1]
                                assert call_kwargs["sender_id"] == "agent-1"

    def test_send_message_auto_detect_failure(self, capsys):
        """Test send-message fails when auto-detection fails."""
        args = argparse.Namespace(
            sender_id=None,  # No sender ID provided
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

    def test_broadcast_message_auto_detect_success(self, tmp_path, capsys):
        """Test broadcast-message with successful auto-detection."""
        registry_data = {
            "session_name": "test",
            "updated_at": "2025-11-18T10:00:00Z",
            "agents": [
                {
                    "id": "agent-1",
                    "pane_index": "test:0.0",
                    "pid": 12345,
                    "status": "active",
                    "last_seen": "2025-11-18T10:00:00Z",
                    "session_name": "test",
                    "tmux_pane_id": "%2",
                }
            ],
        }

        registry_path = tmp_path / "ACTIVE_AGENTS.json"
        registry_path.write_text(json.dumps(registry_data))

        args = argparse.Namespace(
            sender_id=None,  # No sender ID provided
            type="INFO",
            content="Broadcast test",
            include_self=False,
            json=False,
            verbose=False,
        )

        with patch.dict(os.environ, {"TMUX_PANE": "%2"}):
            with patch("claudeswarm.project.get_active_agents_path", return_value=registry_path):
                with mock_pid_alive():
                    with patch("claudeswarm.cli.validate_agent_id", side_effect=lambda x: x):
                        with patch("claudeswarm.cli.validate_message_content", side_effect=lambda x: x):
                            with patch("claudeswarm.messaging.broadcast_message") as mock_broadcast:
                                mock_broadcast.return_value = {"agent-2": True}

                                with pytest.raises(SystemExit) as exc_info:
                                    cmd_broadcast_message(args)

                                assert exc_info.value.code == 0
                                # Verify the call used auto-detected sender ID
                                call_kwargs = mock_broadcast.call_args[1]
                                assert call_kwargs["sender_id"] == "agent-1"

    def test_broadcast_message_auto_detect_failure(self, capsys):
        """Test broadcast-message fails when auto-detection fails."""
        args = argparse.Namespace(
            sender_id=None,  # No sender ID provided
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
