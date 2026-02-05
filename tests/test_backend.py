"""Tests for the backend abstraction module.

Tests cover:
- AgentInfo dataclass
- Auto-detection logic (env var, config, TMUX env, default)
- Singleton behavior (get_backend / reset_backend)
- TerminalBackend ABC contract
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from claudeswarm.backend import (
    AgentInfo,
    TerminalBackend,
    detect_backend,
    get_backend,
    reset_backend,
)


class TestAgentInfo:
    """Tests for the AgentInfo dataclass."""

    def test_basic_creation(self):
        info = AgentInfo(
            agent_id="agent-0",
            pid=12345,
            identifier="%5",
            session_name="main",
        )
        assert info.agent_id == "agent-0"
        assert info.pid == 12345
        assert info.identifier == "%5"
        assert info.session_name == "main"
        assert info.status == "active"
        assert info.cwd is None
        assert info.metadata == {}

    def test_creation_with_all_fields(self):
        info = AgentInfo(
            agent_id="agent-1",
            pid=99999,
            identifier="/dev/ttys005",
            session_name="ghostty",
            status="stale",
            cwd="/home/user/project",
            metadata={"tty": "/dev/ttys005", "ppid": 100},
        )
        assert info.status == "stale"
        assert info.cwd == "/home/user/project"
        assert info.metadata["tty"] == "/dev/ttys005"
        assert info.metadata["ppid"] == 100

    def test_metadata_default_is_independent(self):
        """Each instance should get its own metadata dict."""
        info1 = AgentInfo(agent_id="a", pid=1, identifier="x", session_name="s")
        info2 = AgentInfo(agent_id="b", pid=2, identifier="y", session_name="s")
        info1.metadata["key"] = "value"
        assert "key" not in info2.metadata


class TestDetectBackend:
    """Tests for the detect_backend() function."""

    @patch.dict(os.environ, {"CLAUDESWARM_BACKEND": "tmux"}, clear=False)
    def test_env_var_tmux(self):
        backend = detect_backend()
        assert backend.name == "tmux"

    @patch.dict(os.environ, {"CLAUDESWARM_BACKEND": "process"}, clear=False)
    def test_env_var_process(self):
        backend = detect_backend()
        assert backend.name == "process"

    @patch.dict(os.environ, {"CLAUDESWARM_BACKEND": "TMUX"}, clear=False)
    def test_env_var_case_insensitive(self):
        backend = detect_backend()
        assert backend.name == "tmux"

    @patch.dict(os.environ, {"CLAUDESWARM_BACKEND": " process "}, clear=False)
    def test_env_var_strips_whitespace(self):
        backend = detect_backend()
        assert backend.name == "process"

    def test_env_var_unknown_falls_through(self):
        """Unknown env var value should fall through to auto-detection."""
        env = os.environ.copy()
        env.pop("TMUX", None)
        env.pop("TMUX_PANE", None)
        env["CLAUDESWARM_BACKEND"] = "invalid_backend"
        with patch.dict(os.environ, env, clear=True):
            with patch("claudeswarm.config.get_config", side_effect=Exception("no config")):
                backend = detect_backend()
                assert backend.name == "process"

    @patch.dict(
        os.environ,
        {"TMUX": "/tmp/tmux-501/default,12345,0", "CLAUDESWARM_BACKEND": ""},
        clear=False,
    )
    def test_tmux_env_detected(self):
        """TMUX env var should trigger TmuxBackend."""
        with patch("claudeswarm.config.get_config", side_effect=Exception("no config")):
            backend = detect_backend()
            assert backend.name == "tmux"

    def test_tmux_pane_env_detected(self):
        """TMUX_PANE env var alone should trigger TmuxBackend."""
        env = os.environ.copy()
        env.pop("TMUX", None)
        env["TMUX_PANE"] = "%5"
        env["CLAUDESWARM_BACKEND"] = ""
        with patch.dict(os.environ, env, clear=True):
            with patch("claudeswarm.config.get_config", side_effect=Exception("no config")):
                backend = detect_backend()
                assert backend.name == "tmux"

    def test_default_is_process_backend(self):
        """Without TMUX or env override, default should be ProcessBackend."""
        env = os.environ.copy()
        env.pop("TMUX", None)
        env.pop("TMUX_PANE", None)
        env.pop("CLAUDESWARM_BACKEND", None)
        with patch.dict(os.environ, env, clear=True):
            with patch("claudeswarm.config.get_config", side_effect=Exception("no config")):
                backend = detect_backend()
                assert backend.name == "process"

    def test_config_provider_tmux(self):
        """Config file provider=tmux should use TmuxBackend."""
        env = os.environ.copy()
        env.pop("TMUX", None)
        env.pop("TMUX_PANE", None)
        env.pop("CLAUDESWARM_BACKEND", None)

        mock_config = MagicMock()
        mock_config.backend.provider = "tmux"

        with patch.dict(os.environ, env, clear=True):
            with patch("claudeswarm.config.get_config", return_value=mock_config):
                backend = detect_backend()
                assert backend.name == "tmux"

    def test_config_provider_process(self):
        """Config file provider=process should use ProcessBackend."""
        env = os.environ.copy()
        env.pop("TMUX", None)
        env.pop("TMUX_PANE", None)
        env.pop("CLAUDESWARM_BACKEND", None)

        mock_config = MagicMock()
        mock_config.backend.provider = "process"

        with patch.dict(os.environ, env, clear=True):
            with patch("claudeswarm.config.get_config", return_value=mock_config):
                backend = detect_backend()
                assert backend.name == "process"

    def test_config_provider_auto_falls_through(self):
        """Config provider=auto should fall through to env detection."""
        env = os.environ.copy()
        env.pop("TMUX", None)
        env.pop("TMUX_PANE", None)
        env.pop("CLAUDESWARM_BACKEND", None)

        mock_config = MagicMock()
        mock_config.backend.provider = "auto"

        with patch.dict(os.environ, env, clear=True):
            with patch("claudeswarm.config.get_config", return_value=mock_config):
                backend = detect_backend()
                assert backend.name == "process"

    def test_env_var_overrides_config(self):
        """CLAUDESWARM_BACKEND env var should take priority over config."""
        mock_config = MagicMock()
        mock_config.backend.provider = "tmux"

        with patch.dict(os.environ, {"CLAUDESWARM_BACKEND": "process"}, clear=False):
            with patch("claudeswarm.config.get_config", return_value=mock_config):
                backend = detect_backend()
                assert backend.name == "process"


class TestSingleton:
    """Tests for get_backend / reset_backend singleton management."""

    def test_get_backend_returns_same_instance(self):
        """get_backend() should return the same instance on repeated calls."""
        env = os.environ.copy()
        env.pop("TMUX", None)
        env.pop("TMUX_PANE", None)
        env.pop("CLAUDESWARM_BACKEND", None)
        with patch.dict(os.environ, env, clear=True):
            reset_backend()
            b1 = get_backend()
            b2 = get_backend()
            assert b1 is b2

    def test_reset_backend_clears_instance(self):
        """reset_backend() should clear the cached instance."""
        env = os.environ.copy()
        env.pop("TMUX", None)
        env.pop("TMUX_PANE", None)
        env.pop("CLAUDESWARM_BACKEND", None)
        with patch.dict(os.environ, env, clear=True):
            reset_backend()
            b1 = get_backend()
            reset_backend()
            b2 = get_backend()
            # They should be equal in type but different objects
            assert type(b1) is type(b2)
            assert b1 is not b2


class TestTerminalBackendABC:
    """Tests for the TerminalBackend abstract base class."""

    def test_cannot_instantiate_directly(self):
        """TerminalBackend should not be directly instantiable."""
        with pytest.raises(TypeError):
            TerminalBackend()

    def test_create_monitoring_pane_default(self):
        """Default create_monitoring_pane should return None."""

        class MinimalBackend(TerminalBackend):
            @property
            def name(self):
                return "test"

            def discover_agents(self, project_root=None):
                return []

            def send_message(self, target_identifier, message):
                return False

            def verify_agent(self, identifier):
                return False

            def get_current_agent_identifier(self):
                return None

        backend = MinimalBackend()
        assert backend.create_monitoring_pane() is None
