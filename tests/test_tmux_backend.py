"""Tests for the tmux terminal backend.

Tests cover:
- Backend name and properties
- Agent discovery via tmux panes
- Message sending via tmux send-keys
- Agent verification via pane existence check
- Current agent identification via TMUX_PANE
- Monitoring pane creation
- Error handling
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from claudeswarm.tmux_backend import TmuxBackend


class TestTmuxBackendProperties:
    """Tests for TmuxBackend basic properties."""

    def test_name(self):
        backend = TmuxBackend()
        assert backend.name == "tmux"


class TestTmuxBackendDiscovery:
    """Tests for TmuxBackend.discover_agents()."""

    @patch("claudeswarm.discovery._get_process_cwd")
    @patch("claudeswarm.discovery._is_claude_code_process")
    @patch("claudeswarm.discovery._parse_tmux_panes")
    def test_discover_agents_basic(self, mock_panes, mock_is_claude, mock_cwd):
        mock_panes.return_value = [
            {
                "session_name": "main",
                "pane_index": "0",
                "tmux_pane_id": "%0",
                "pid": 100,
                "command": "claude",
            },
            {
                "session_name": "main",
                "pane_index": "1",
                "tmux_pane_id": "%1",
                "pid": 200,
                "command": "vim",
            },
        ]
        mock_is_claude.side_effect = lambda cmd, pid: "claude" in cmd
        mock_cwd.return_value = "/home/user/project"

        backend = TmuxBackend()
        agents = backend.discover_agents()

        assert len(agents) == 1
        assert agents[0].pid == 100
        assert agents[0].identifier == "%0"
        assert agents[0].session_name == "main"
        assert agents[0].cwd == "/home/user/project"

    @patch("claudeswarm.discovery._get_process_cwd")
    @patch("claudeswarm.discovery._is_claude_code_process")
    @patch("claudeswarm.discovery._parse_tmux_panes")
    def test_discover_agents_filters_by_project(self, mock_panes, mock_is_claude, mock_cwd):
        mock_panes.return_value = [
            {
                "session_name": "main",
                "pane_index": "0",
                "tmux_pane_id": "%0",
                "pid": 100,
                "command": "claude",
            },
            {
                "session_name": "main",
                "pane_index": "1",
                "tmux_pane_id": "%1",
                "pid": 200,
                "command": "claude",
            },
        ]
        mock_is_claude.return_value = True
        mock_cwd.side_effect = lambda pid: {
            100: "/home/user/project-a",
            200: "/home/user/project-b",
        }[pid]

        backend = TmuxBackend()
        agents = backend.discover_agents(project_root="/home/user/project-a")

        assert len(agents) == 1
        assert agents[0].pid == 100

    @patch("claudeswarm.discovery._parse_tmux_panes")
    def test_discover_agents_tmux_error(self, mock_panes):
        mock_panes.side_effect = RuntimeError("tmux not running")

        backend = TmuxBackend()
        agents = backend.discover_agents()

        assert agents == []

    @patch("claudeswarm.discovery._get_process_cwd")
    @patch("claudeswarm.discovery._is_claude_code_process")
    @patch("claudeswarm.discovery._parse_tmux_panes")
    def test_discover_agents_multiple(self, mock_panes, mock_is_claude, mock_cwd):
        mock_panes.return_value = [
            {
                "session_name": "work",
                "pane_index": "0",
                "tmux_pane_id": "%5",
                "pid": 100,
                "command": "claude",
            },
            {
                "session_name": "work",
                "pane_index": "1",
                "tmux_pane_id": "%6",
                "pid": 200,
                "command": "claude --model opus",
            },
        ]
        mock_is_claude.return_value = True
        mock_cwd.return_value = "/home/user/project"

        backend = TmuxBackend()
        agents = backend.discover_agents()

        assert len(agents) == 2
        assert agents[0].metadata["tmux_pane_id"] == "%5"
        assert agents[1].metadata["tmux_pane_id"] == "%6"

    @patch("claudeswarm.discovery._get_process_cwd")
    @patch("claudeswarm.discovery._is_claude_code_process")
    @patch("claudeswarm.discovery._parse_tmux_panes")
    def test_discover_agents_uses_pane_index_fallback(self, mock_panes, mock_is_claude, mock_cwd):
        """When tmux_pane_id is missing, should use pane_index as identifier."""
        mock_panes.return_value = [
            {
                "session_name": "main",
                "pane_index": "2",
                "pid": 100,
                "command": "claude",
            },
        ]
        mock_is_claude.return_value = True
        mock_cwd.return_value = None

        backend = TmuxBackend()
        agents = backend.discover_agents()

        assert len(agents) == 1
        assert agents[0].identifier == "2"


class TestTmuxBackendMessaging:
    """Tests for TmuxBackend.send_message()."""

    @patch("claudeswarm.messaging.TmuxMessageDelivery")
    def test_send_message_success(self, mock_delivery_cls):
        mock_delivery_cls.send_to_pane.return_value = True

        backend = TmuxBackend()
        result = backend.send_message("%5", "hello agent")

        assert result is True
        mock_delivery_cls.send_to_pane.assert_called_once_with("%5", "hello agent")

    @patch("claudeswarm.messaging.TmuxMessageDelivery")
    def test_send_message_failure(self, mock_delivery_cls):
        mock_delivery_cls.send_to_pane.return_value = False

        backend = TmuxBackend()
        result = backend.send_message("%5", "hello agent")

        assert result is False

    @patch("claudeswarm.messaging.TmuxMessageDelivery")
    def test_send_message_exception(self, mock_delivery_cls):
        mock_delivery_cls.send_to_pane.side_effect = Exception("tmux died")

        backend = TmuxBackend()
        result = backend.send_message("%5", "hello agent")

        assert result is False


class TestTmuxBackendVerify:
    """Tests for TmuxBackend.verify_agent()."""

    @patch("claudeswarm.messaging.TmuxMessageDelivery")
    def test_verify_agent_exists(self, mock_delivery_cls):
        mock_delivery_cls.verify_pane_exists.return_value = True

        backend = TmuxBackend()
        assert backend.verify_agent("%5") is True

    @patch("claudeswarm.messaging.TmuxMessageDelivery")
    def test_verify_agent_not_exists(self, mock_delivery_cls):
        mock_delivery_cls.verify_pane_exists.return_value = False

        backend = TmuxBackend()
        assert backend.verify_agent("%99") is False


class TestTmuxBackendIdentity:
    """Tests for TmuxBackend.get_current_agent_identifier()."""

    def test_returns_tmux_pane(self):
        backend = TmuxBackend()
        with patch.dict(os.environ, {"TMUX_PANE": "%5"}):
            assert backend.get_current_agent_identifier() == "%5"

    def test_returns_none_without_tmux_pane(self):
        backend = TmuxBackend()
        env = os.environ.copy()
        env.pop("TMUX_PANE", None)
        with patch.dict(os.environ, env, clear=True):
            assert backend.get_current_agent_identifier() is None


class TestTmuxBackendMonitoring:
    """Tests for TmuxBackend.create_monitoring_pane()."""

    @patch("claudeswarm.monitoring.create_tmux_monitoring_pane")
    def test_create_monitoring_pane_success(self, mock_create):
        mock_create.return_value = "%10"

        backend = TmuxBackend()
        result = backend.create_monitoring_pane()

        assert result == "%10"
        mock_create.assert_called_once()

    @patch("claudeswarm.monitoring.create_tmux_monitoring_pane")
    def test_create_monitoring_pane_failure(self, mock_create):
        mock_create.return_value = None

        backend = TmuxBackend()
        result = backend.create_monitoring_pane()

        assert result is None
