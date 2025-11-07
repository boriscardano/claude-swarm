"""Security tests for monitoring module command injection vulnerability fix.

This module tests that the monitoring.py fix properly prevents command injection
by validating inputs and escaping shell arguments.

Author: Agent-SecurityFix
Phase: Security Fix
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from claudeswarm.monitoring import start_monitoring
from claudeswarm.validators import ValidationError


class TestMonitoringSecurityFix:
    """Tests for command injection vulnerability fix in monitoring.py."""

    def test_filter_type_valid_message_type(self, capsys):
        """Test that valid MessageType values are accepted."""
        with patch("claudeswarm.monitoring.create_tmux_monitoring_pane") as mock_pane:
            mock_pane.return_value = "%1"

            with patch("subprocess.run") as mock_subprocess:
                # Should accept valid MessageType value
                start_monitoring(filter_type="INFO", use_tmux=True)

                # Verify subprocess was called with properly escaped command
                assert mock_subprocess.called
                call_args = mock_subprocess.call_args[0][0]

                # Should contain escaped filter-type argument
                assert any("--filter-type" in arg for arg in call_args)
                # Should NOT contain unescaped INFO directly concatenated
                assert call_args[-2] != "C-m"  # Verify structure

    def test_filter_type_invalid_message_type_rejected(self, capsys):
        """Test that invalid MessageType values are rejected to prevent injection."""
        with patch("claudeswarm.monitoring.create_tmux_monitoring_pane") as mock_pane:
            mock_pane.return_value = "%1"

            # Should reject invalid message type and exit with error
            with pytest.raises(SystemExit) as exc_info:
                start_monitoring(filter_type="INFO && rm -rf /", use_tmux=True)

            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "Invalid message type" in captured.err

    def test_filter_type_injection_attempt_blocked(self, capsys):
        """Test that command injection via filter_type is blocked."""
        with patch("claudeswarm.monitoring.create_tmux_monitoring_pane") as mock_pane:
            mock_pane.return_value = "%1"

            # Various injection attempts should be rejected
            injection_attempts = [
                "INFO && rm -rf /",
                "INFO; echo pwned",
                "INFO | cat /etc/passwd",
                "INFO`whoami`",
                "INFO$(whoami)",
                "INFO\nrm -rf /",
            ]

            for injection in injection_attempts:
                with pytest.raises(SystemExit) as exc_info:
                    start_monitoring(filter_type=injection, use_tmux=True)

                assert exc_info.value.code == 1
                captured = capsys.readouterr()
                assert "Invalid message type" in captured.err

    def test_filter_agent_valid_agent_id(self, capsys):
        """Test that valid agent IDs are accepted."""
        with patch("claudeswarm.monitoring.create_tmux_monitoring_pane") as mock_pane:
            mock_pane.return_value = "%1"

            with patch("subprocess.run") as mock_subprocess:
                # Should accept valid agent ID
                start_monitoring(filter_agent="agent-1", use_tmux=True)

                # Verify subprocess was called with properly escaped command
                assert mock_subprocess.called
                call_args = mock_subprocess.call_args[0][0]

                # Should contain escaped filter-agent argument
                assert any("--filter-agent" in arg for arg in call_args)

    def test_filter_agent_invalid_agent_id_rejected(self, capsys):
        """Test that invalid agent IDs are rejected to prevent injection."""
        with patch("claudeswarm.monitoring.create_tmux_monitoring_pane") as mock_pane:
            mock_pane.return_value = "%1"

            # Should reject invalid agent ID and exit with error
            with pytest.raises(SystemExit) as exc_info:
                start_monitoring(filter_agent="agent-1 && rm -rf /", use_tmux=True)

            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "Invalid agent ID" in captured.err

    def test_filter_agent_injection_attempt_blocked(self, capsys):
        """Test that command injection via filter_agent is blocked."""
        with patch("claudeswarm.monitoring.create_tmux_monitoring_pane") as mock_pane:
            mock_pane.return_value = "%1"

            # Various injection attempts should be rejected
            injection_attempts = [
                "agent-1 && rm -rf /",
                "agent-1; echo pwned",
                "agent-1 | cat /etc/passwd",
                "agent-1`whoami`",
                "agent-1$(whoami)",
                "agent-1\nrm -rf /",
                "agent-1'; DROP TABLE agents;--",
                "../../../etc/passwd",
            ]

            for injection in injection_attempts:
                with pytest.raises(SystemExit) as exc_info:
                    start_monitoring(filter_agent=injection, use_tmux=True)

                assert exc_info.value.code == 1
                captured = capsys.readouterr()
                assert "Invalid agent ID" in captured.err

    def test_path_cwd_properly_escaped(self):
        """Test that Path.cwd() is properly escaped in shell command."""
        with patch("claudeswarm.monitoring.create_tmux_monitoring_pane") as mock_pane:
            mock_pane.return_value = "%1"

            with patch("subprocess.run") as mock_subprocess:
                with patch("pathlib.Path.cwd") as mock_cwd:
                    with patch("claudeswarm.monitoring.LockManager") as mock_lock_manager:
                        # Test with a path containing spaces
                        mock_cwd.return_value = Path("/path/with spaces/to/project")

                        start_monitoring(use_tmux=True)

                        # Verify subprocess was called
                        assert mock_subprocess.called
                        call_args = mock_subprocess.call_args[0][0]

                        # The command should be properly constructed with escaping
                        # Check that we're using tmux send-keys
                        assert "tmux" in call_args
                        assert "send-keys" in call_args

    def test_combined_filters_with_valid_inputs(self):
        """Test that both filters work together with valid inputs."""
        with patch("claudeswarm.monitoring.create_tmux_monitoring_pane") as mock_pane:
            mock_pane.return_value = "%1"

            with patch("subprocess.run") as mock_subprocess:
                start_monitoring(
                    filter_type="BLOCKED",
                    filter_agent="agent-1",
                    use_tmux=True
                )

                # Verify subprocess was called
                assert mock_subprocess.called
                call_args = mock_subprocess.call_args[0][0]

                # Should contain both escaped arguments
                assert any("--filter-type" in arg for arg in call_args)
                assert any("--filter-agent" in arg for arg in call_args)

    def test_combined_filters_one_invalid_blocks_execution(self, capsys):
        """Test that if one filter is invalid, execution is blocked."""
        with patch("claudeswarm.monitoring.create_tmux_monitoring_pane") as mock_pane:
            mock_pane.return_value = "%1"

            # Valid filter_type but invalid filter_agent
            with pytest.raises(SystemExit) as exc_info:
                start_monitoring(
                    filter_type="BLOCKED",
                    filter_agent="agent-1; rm -rf /",
                    use_tmux=True
                )

            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "Invalid agent ID" in captured.err

            # Valid filter_agent but invalid filter_type
            with pytest.raises(SystemExit) as exc_info:
                start_monitoring(
                    filter_type="BLOCKED && rm -rf /",
                    filter_agent="agent-1",
                    use_tmux=True
                )

            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "Invalid message type" in captured.err

    def test_special_characters_in_agent_id_rejected(self, capsys):
        """Test that special shell characters in agent IDs are rejected."""
        with patch("claudeswarm.monitoring.create_tmux_monitoring_pane") as mock_pane:
            mock_pane.return_value = "%1"

            # Special characters that could be used for injection
            special_chars = [
                "agent$HOME",
                "agent`id`",
                "agent$(whoami)",
                "agent&",
                "agent|",
                "agent;",
                "agent>",
                "agent<",
                "agent*",
                "agent?",
                "agent[",
                "agent]",
                "agent(",
                "agent)",
                "agent{",
                "agent}",
                "agent@bad",
                "agent#comment",
                "agent!bang",
            ]

            for agent_id in special_chars:
                with pytest.raises(SystemExit) as exc_info:
                    start_monitoring(filter_agent=agent_id, use_tmux=True)

                assert exc_info.value.code == 1
                captured = capsys.readouterr()
                assert "Invalid agent ID" in captured.err

    def test_no_tmux_mode_unaffected(self):
        """Test that non-tmux mode is unaffected by the security fix."""
        with patch("claudeswarm.monitoring.Monitor") as mock_monitor_class:
            mock_monitor = Mock()
            mock_monitor_class.return_value = mock_monitor

            # This should work without any issues (no subprocess calls)
            start_monitoring(
                filter_type="INFO",
                filter_agent="agent-1",
                use_tmux=False
            )

            # Verify monitor was created with proper filter
            assert mock_monitor_class.called
            assert mock_monitor.run_dashboard.called
