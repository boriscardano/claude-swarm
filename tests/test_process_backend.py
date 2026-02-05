"""Tests for the process-based terminal backend.

Tests cover:
- Terminal name detection
- Claude Code process discovery via ps
- CWD-based project filtering
- TTY-based identity
- PID and TTY-based agent verification
- send_message always returns False
- create_monitoring_pane always returns None
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from claudeswarm.process_backend import (
    ProcessBackend,
    _detect_terminal_name,
    _find_claude_processes,
)


class TestDetectTerminalName:
    """Tests for _detect_terminal_name() helper."""

    def test_ghostty_detected(self):
        with patch.dict(os.environ, {"GHOSTTY_RESOURCES_DIR": "/usr/share/ghostty"}, clear=False):
            assert _detect_terminal_name() == "ghostty"

    def test_iterm2_detected(self):
        env = os.environ.copy()
        env.pop("GHOSTTY_RESOURCES_DIR", None)
        env["TERM_PROGRAM"] = "iTerm.app"
        with patch.dict(os.environ, env, clear=True):
            assert _detect_terminal_name() == "iterm.app"

    def test_terminal_app_detected(self):
        env = os.environ.copy()
        env.pop("GHOSTTY_RESOURCES_DIR", None)
        env["TERM_PROGRAM"] = "Apple_Terminal"
        with patch.dict(os.environ, env, clear=True):
            assert _detect_terminal_name() == "apple_terminal"

    def test_unknown_terminal(self):
        env = os.environ.copy()
        env.pop("GHOSTTY_RESOURCES_DIR", None)
        env.pop("TERM_PROGRAM", None)
        with patch.dict(os.environ, env, clear=True):
            assert _detect_terminal_name() == "unknown"

    def test_ghostty_takes_precedence_over_term_program(self):
        with patch.dict(
            os.environ,
            {"GHOSTTY_RESOURCES_DIR": "/usr/share/ghostty", "TERM_PROGRAM": "iTerm.app"},
            clear=False,
        ):
            assert _detect_terminal_name() == "ghostty"


class TestFindClaudeProcesses:
    """Tests for _find_claude_processes()."""

    def _make_ps_output(self, lines):
        """Helper to create ps output from a list of (pid, ppid, tty, command) tuples."""
        return "\n".join(f"{pid} {ppid} {tty} {cmd}" for pid, ppid, tty, cmd in lines)

    @patch("claudeswarm.process_backend.os.getpid", return_value=99999)
    @patch("claudeswarm.process_backend.subprocess.run")
    def test_finds_claude_processes(self, mock_run, mock_getpid):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=self._make_ps_output(
                [
                    (100, 1, "ttys001", "claude"),
                    (101, 1, "ttys002", "/usr/local/bin/claude --model opus"),
                    (102, 1, "ttys003", "claude-code"),
                    (200, 1, "ttys004", "vim"),
                ]
            ),
        )
        result = _find_claude_processes()
        assert len(result) == 3
        assert result[0]["pid"] == 100
        assert result[1]["pid"] == 101
        assert result[2]["pid"] == 102

    @patch("claudeswarm.process_backend.os.getpid", return_value=100)
    @patch("claudeswarm.process_backend.subprocess.run")
    def test_excludes_own_process(self, mock_run, mock_getpid):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=self._make_ps_output(
                [
                    (100, 1, "ttys001", "claude"),
                    (101, 1, "ttys002", "claude"),
                ]
            ),
        )
        result = _find_claude_processes()
        assert len(result) == 1
        assert result[0]["pid"] == 101

    @patch("claudeswarm.process_backend.os.getpid", return_value=99999)
    @patch("claudeswarm.process_backend.subprocess.run")
    def test_excludes_claudeswarm_processes(self, mock_run, mock_getpid):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=self._make_ps_output(
                [
                    (100, 1, "ttys001", "claudeswarm discover-agents"),
                    (101, 1, "ttys002", "claude"),
                ]
            ),
        )
        result = _find_claude_processes()
        assert len(result) == 1
        assert result[0]["pid"] == 101

    @patch("claudeswarm.process_backend.os.getpid", return_value=99999)
    @patch("claudeswarm.process_backend.subprocess.run")
    def test_question_mark_tty_becomes_none(self, mock_run, mock_getpid):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=self._make_ps_output(
                [
                    (100, 1, "?", "claude"),
                ]
            ),
        )
        result = _find_claude_processes()
        assert len(result) == 1
        assert result[0]["tty"] is None

    @patch("claudeswarm.process_backend.os.getpid", return_value=99999)
    @patch("claudeswarm.process_backend.subprocess.run")
    def test_ps_timeout(self, mock_run, mock_getpid):
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ps", timeout=3)
        result = _find_claude_processes()
        assert result == []

    @patch("claudeswarm.process_backend.os.getpid", return_value=99999)
    @patch("claudeswarm.process_backend.subprocess.run")
    def test_ps_not_found(self, mock_run, mock_getpid):
        mock_run.side_effect = FileNotFoundError()
        result = _find_claude_processes()
        assert result == []

    @patch("claudeswarm.process_backend.os.getpid", return_value=99999)
    @patch("claudeswarm.process_backend.subprocess.run")
    def test_ps_failure_returns_empty(self, mock_run, mock_getpid):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        result = _find_claude_processes()
        assert result == []


class TestProcessBackend:
    """Tests for the ProcessBackend class."""

    def test_name(self):
        backend = ProcessBackend()
        assert backend.name == "process"

    def test_send_message_always_false(self):
        backend = ProcessBackend()
        assert backend.send_message("/dev/ttys005", "hello") is False

    def test_create_monitoring_pane_returns_none(self):
        backend = ProcessBackend()
        assert backend.create_monitoring_pane() is None

    @patch("claudeswarm.process_backend._find_claude_processes")
    @patch("claudeswarm.process_backend._get_process_cwd_for_pid")
    @patch("claudeswarm.process_backend._detect_terminal_name", return_value="ghostty")
    def test_discover_agents_basic(self, mock_term, mock_cwd, mock_procs):
        mock_procs.return_value = [
            {"pid": 100, "ppid": 1, "tty": "ttys001", "command": "claude"},
            {"pid": 200, "ppid": 1, "tty": "ttys002", "command": "claude --model opus"},
        ]
        mock_cwd.return_value = "/home/user/project"

        backend = ProcessBackend()
        agents = backend.discover_agents()

        assert len(agents) == 2
        assert agents[0].pid == 100
        assert agents[0].identifier == "ttys001"
        assert agents[0].session_name == "ghostty"
        assert agents[0].status == "active"
        assert agents[0].cwd == "/home/user/project"

    @patch("claudeswarm.process_backend._find_claude_processes")
    @patch("claudeswarm.process_backend._get_process_cwd_for_pid")
    @patch("claudeswarm.process_backend._detect_terminal_name", return_value="ghostty")
    def test_discover_agents_filters_by_project_root(self, mock_term, mock_cwd, mock_procs):
        mock_procs.return_value = [
            {"pid": 100, "ppid": 1, "tty": "ttys001", "command": "claude"},
            {"pid": 200, "ppid": 1, "tty": "ttys002", "command": "claude"},
        ]
        mock_cwd.side_effect = lambda pid: {
            100: "/home/user/project-a",
            200: "/home/user/project-b",
        }[pid]

        backend = ProcessBackend()
        agents = backend.discover_agents(project_root="/home/user/project-a")

        assert len(agents) == 1
        assert agents[0].pid == 100

    @patch("claudeswarm.process_backend._find_claude_processes")
    @patch("claudeswarm.process_backend._get_process_cwd_for_pid")
    @patch("claudeswarm.process_backend._detect_terminal_name", return_value="ghostty")
    def test_discover_agents_no_cwd_excluded_when_filtering(self, mock_term, mock_cwd, mock_procs):
        mock_procs.return_value = [
            {"pid": 100, "ppid": 1, "tty": "ttys001", "command": "claude"},
        ]
        mock_cwd.return_value = None

        backend = ProcessBackend()
        agents = backend.discover_agents(project_root="/home/user/project")

        assert len(agents) == 0

    @patch("claudeswarm.process_backend._find_claude_processes")
    @patch("claudeswarm.process_backend._get_process_cwd_for_pid")
    @patch("claudeswarm.process_backend._detect_terminal_name", return_value="ghostty")
    def test_discover_agents_pid_identifier_when_no_tty(self, mock_term, mock_cwd, mock_procs):
        mock_procs.return_value = [
            {"pid": 100, "ppid": 1, "tty": None, "command": "claude"},
        ]
        mock_cwd.return_value = None

        backend = ProcessBackend()
        agents = backend.discover_agents()

        assert len(agents) == 1
        assert agents[0].identifier == "pid:100"


class TestProcessBackendVerify:
    """Tests for ProcessBackend.verify_agent()."""

    def test_verify_pid_alive(self):
        backend = ProcessBackend()
        with patch("claudeswarm.process_backend.os.kill") as mock_kill:
            mock_kill.return_value = None
            # Mock the subprocess call for Claude process verification
            with patch("claudeswarm.process_backend.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(stdout="claude\n")
                with patch("claudeswarm.discovery._is_claude_code_process", return_value=True):
                    assert backend.verify_agent("pid:12345") is True
            mock_kill.assert_called_once_with(12345, 0)

    def test_verify_pid_alive_not_claude_anymore(self):
        """PID exists but is no longer a Claude process (PID reuse)."""
        backend = ProcessBackend()
        with patch("claudeswarm.process_backend.os.kill") as mock_kill:
            mock_kill.return_value = None
            with patch("claudeswarm.process_backend.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(stdout="vim\n")
                with patch("claudeswarm.discovery._is_claude_code_process", return_value=False):
                    assert backend.verify_agent("pid:12345") is False

    def test_verify_pid_dead(self):
        backend = ProcessBackend()
        with patch("claudeswarm.process_backend.os.kill", side_effect=ProcessLookupError):
            assert backend.verify_agent("pid:12345") is False

    def test_verify_pid_invalid(self):
        backend = ProcessBackend()
        assert backend.verify_agent("pid:notanumber") is False

    def test_verify_tty_exists(self):
        backend = ProcessBackend()
        with patch("claudeswarm.process_backend.Path") as MockPath:
            mock_resolved = MagicMock()
            mock_resolved.__str__ = lambda self: "/dev/ttys999"
            mock_resolved.exists.return_value = True
            mock_path_instance = MagicMock()
            mock_path_instance.resolve.return_value = mock_resolved
            MockPath.return_value = mock_path_instance
            assert backend.verify_agent("/dev/ttys999") is True

    def test_verify_tty_missing(self):
        backend = ProcessBackend()
        with patch("claudeswarm.process_backend.Path") as MockPath:
            mock_resolved = MagicMock()
            mock_resolved.__str__ = lambda self: "/dev/ttys_nonexistent"
            mock_resolved.exists.return_value = False
            mock_path_instance = MagicMock()
            mock_path_instance.resolve.return_value = mock_resolved
            MockPath.return_value = mock_path_instance
            assert backend.verify_agent("/dev/ttys_nonexistent") is False

    def test_verify_tty_path_traversal_blocked(self):
        """Path traversal attempts should be rejected."""
        backend = ProcessBackend()
        with patch("claudeswarm.process_backend.Path") as MockPath:
            # Simulate resolve() returning a path outside /dev/
            mock_resolved = MagicMock()
            mock_resolved.__str__ = lambda self: "/etc/passwd"
            mock_resolved.exists.return_value = True
            mock_path_instance = MagicMock()
            mock_path_instance.resolve.return_value = mock_resolved
            MockPath.return_value = mock_path_instance
            assert backend.verify_agent("/dev/../../etc/passwd") is False

    def test_verify_bare_tty_name(self):
        backend = ProcessBackend()
        # Bare TTY names get /dev/ prefixed after pattern validation
        with patch.object(Path, "resolve") as mock_resolve:
            mock_resolved = MagicMock()
            mock_resolved.__str__ = lambda self: "/dev/ttys005"
            mock_resolved.exists.return_value = True
            mock_resolve.return_value = mock_resolved
            assert backend.verify_agent("ttys005") is True

    def test_verify_bare_tty_pts_name(self):
        """Linux pts/ style TTY names should also work."""
        backend = ProcessBackend()
        with patch.object(Path, "resolve") as mock_resolve:
            mock_resolved = MagicMock()
            mock_resolved.__str__ = lambda self: "/dev/pts/3"
            mock_resolved.exists.return_value = True
            mock_resolve.return_value = mock_resolved
            assert backend.verify_agent("pts/3") is True

    def test_verify_unknown_identifier(self):
        backend = ProcessBackend()
        assert backend.verify_agent("some-unknown-id") is False

    def test_verify_bare_tty_invalid_pattern(self):
        """Invalid TTY patterns should be rejected."""
        backend = ProcessBackend()
        assert backend.verify_agent("../../etc/passwd") is False
        assert backend.verify_agent("notadevice") is False


class TestProcessBackendIdentity:
    """Tests for ProcessBackend.get_current_agent_identifier()."""

    def test_gets_stdout_tty(self):
        backend = ProcessBackend()
        with patch("claudeswarm.process_backend.os.ttyname", return_value="/dev/ttys005"):
            with patch("claudeswarm.process_backend.sys.stdout") as mock_stdout:
                mock_stdout.fileno.return_value = 1
                result = backend.get_current_agent_identifier()
                assert result == "/dev/ttys005"

    def test_falls_back_to_stdin(self):
        backend = ProcessBackend()

        def ttyname_side_effect(fd):
            if fd == 1:  # stdout
                raise OSError("not a tty")
            return "/dev/ttys005"

        with patch("claudeswarm.process_backend.os.ttyname", side_effect=ttyname_side_effect):
            with patch("claudeswarm.process_backend.sys.stdout") as mock_stdout:
                mock_stdout.fileno.return_value = 1
                with patch("claudeswarm.process_backend.sys.stdin") as mock_stdin:
                    mock_stdin.fileno.return_value = 0
                    result = backend.get_current_agent_identifier()
                    assert result == "/dev/ttys005"

    def test_returns_none_when_no_tty(self):
        backend = ProcessBackend()
        with patch("claudeswarm.process_backend.sys.stdout") as mock_stdout:
            mock_stdout.fileno.side_effect = OSError("not a tty")
            with patch("claudeswarm.process_backend.sys.stdin") as mock_stdin:
                mock_stdin.fileno.side_effect = OSError("not a tty")
                with patch("claudeswarm.process_backend.os.open", side_effect=OSError):
                    result = backend.get_current_agent_identifier()
                    assert result is None
