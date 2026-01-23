"""
Comprehensive unit tests for the CLI module.

Tests cover:
- All CLI commands: discover-agents, list-agents, acquire/release locks, etc.
- Argument parsing and validation
- Output formatting (text and JSON)
- Error handling and exit codes
- Mocked subprocess calls to tmux
- Mocked file system operations

Author: Agent-TestCoverage
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from claudeswarm.cli import (
    cmd_acquire_file_lock,
    cmd_cleanup_stale_locks,
    cmd_discover_agents,
    cmd_list_agents,
    cmd_list_all_locks,
    cmd_release_file_lock,
    cmd_start_monitoring,
    cmd_who_has_lock,
    format_timestamp,
    main,
    print_help,
    print_version,
)


class TestFormatTimestamp:
    """Tests for timestamp formatting function."""

    def test_format_timestamp_basic(self):
        """Test basic timestamp formatting."""
        ts = 1609459200.0  # 2021-01-01 00:00:00 UTC
        result = format_timestamp(ts)
        assert "2021-01-01" in result
        assert "UTC" in result

    def test_format_timestamp_now(self):
        """Test formatting current timestamp."""
        import time

        ts = time.time()
        result = format_timestamp(ts)
        assert isinstance(result, str)
        assert "UTC" in result

    def test_format_timestamp_zero(self):
        """Test formatting zero timestamp."""
        result = format_timestamp(0.0)
        assert "1970-01-01" in result


class TestAcquireFileLock:
    """Tests for acquire-file-lock command."""

    def test_acquire_lock_success(self, capsys):
        """Test successful lock acquisition."""
        args = argparse.Namespace(
            project_root=Path("/test/root"),
            filepath="test.txt",
            agent_id="agent-1",
            reason="testing",
        )

        with patch("claudeswarm.cli.LockManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager.acquire_lock.return_value = (True, None)
            mock_manager_class.return_value = mock_manager

            with pytest.raises(SystemExit) as exc_info:
                cmd_acquire_file_lock(args)

            assert exc_info.value.code == 0
            captured = capsys.readouterr()
            assert "Lock acquired" in captured.out
            assert "agent-1" in captured.out
            assert "testing" in captured.out

    def test_acquire_lock_conflict(self, capsys):
        """Test lock acquisition with conflict."""
        args = argparse.Namespace(
            project_root=Path("/test/root"),
            filepath="test.txt",
            agent_id="agent-1",
            reason="testing",
        )

        mock_conflict = Mock()
        mock_conflict.current_holder = "agent-2"
        mock_conflict.locked_at = datetime(2021, 1, 1, 0, 0, 0, tzinfo=UTC)
        mock_conflict.reason = "other reason"

        with patch("claudeswarm.cli.LockManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager.acquire_lock.return_value = (False, mock_conflict)
            mock_manager_class.return_value = mock_manager

            with pytest.raises(SystemExit) as exc_info:
                cmd_acquire_file_lock(args)

            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "Lock conflict" in captured.err
            assert "agent-2" in captured.err

    def test_acquire_lock_no_reason(self, capsys):
        """Test lock acquisition without reason."""
        args = argparse.Namespace(
            project_root=Path("/test/root"),
            filepath="test.txt",
            agent_id="agent-1",
            reason=None,
        )

        with patch("claudeswarm.cli.LockManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager.acquire_lock.return_value = (True, None)
            mock_manager_class.return_value = mock_manager

            with pytest.raises(SystemExit) as exc_info:
                cmd_acquire_file_lock(args)

            assert exc_info.value.code == 0
            mock_manager.acquire_lock.assert_called_once_with(
                filepath="test.txt", agent_id="agent-1", reason=""
            )

    def test_acquire_lock_with_auto_detect(self, capsys, tmp_path):
        """Test lock acquisition with auto-detected agent ID."""
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
            project_root=tmp_path,
            filepath="test.txt",
            agent_id=None,  # Auto-detect
            reason="testing",
        )

        with patch.dict(os.environ, {"TMUX_PANE": "%99"}):
            with patch("claudeswarm.project.get_active_agents_path", return_value=registry_path):
                with patch("claudeswarm.cli.LockManager") as mock_manager_class:
                    mock_manager = Mock()
                    mock_manager.acquire_lock.return_value = (True, None)
                    mock_manager_class.return_value = mock_manager

                    with pytest.raises(SystemExit) as exc_info:
                        cmd_acquire_file_lock(args)

                    assert exc_info.value.code == 0
                    # Verify auto-detected agent ID was used
                    call_kwargs = mock_manager.acquire_lock.call_args[1]
                    assert call_kwargs["agent_id"] == "agent-auto"

    def test_acquire_lock_auto_detect_fails(self, capsys):
        """Test lock acquisition fails when auto-detect fails."""
        import os

        args = argparse.Namespace(
            project_root=Path("/test/root"),
            filepath="test.txt",
            agent_id=None,  # Auto-detect
            reason="testing",
        )

        with patch.dict(os.environ, {}, clear=True):  # No TMUX_PANE
            with pytest.raises(SystemExit) as exc_info:
                cmd_acquire_file_lock(args)

            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "Could not auto-detect agent identity" in captured.err


class TestReleaseFileLock:
    """Tests for release-file-lock command."""

    def test_release_lock_success(self, capsys):
        """Test successful lock release."""
        args = argparse.Namespace(
            project_root=Path("/test/root"),
            filepath="test.txt",
            agent_id="agent-1",
        )

        with patch("claudeswarm.cli.LockManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager.release_lock.return_value = True
            mock_manager_class.return_value = mock_manager

            with pytest.raises(SystemExit) as exc_info:
                cmd_release_file_lock(args)

            assert exc_info.value.code == 0
            captured = capsys.readouterr()
            assert "Lock released" in captured.out

    def test_release_lock_failure(self, capsys):
        """Test failed lock release."""
        args = argparse.Namespace(
            project_root=Path("/test/root"),
            filepath="test.txt",
            agent_id="agent-1",
        )

        with patch("claudeswarm.cli.LockManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager.release_lock.return_value = False
            mock_manager_class.return_value = mock_manager

            with pytest.raises(SystemExit) as exc_info:
                cmd_release_file_lock(args)

            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "Failed to release lock" in captured.err

    def test_release_lock_with_auto_detect(self, capsys, tmp_path):
        """Test lock release with auto-detected agent ID."""
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
            project_root=tmp_path, filepath="test.txt", agent_id=None  # Auto-detect
        )

        with patch.dict(os.environ, {"TMUX_PANE": "%99"}):
            with patch("claudeswarm.project.get_active_agents_path", return_value=registry_path):
                with patch("claudeswarm.cli.LockManager") as mock_manager_class:
                    mock_manager = Mock()
                    mock_manager.release_lock.return_value = True
                    mock_manager_class.return_value = mock_manager

                    with pytest.raises(SystemExit) as exc_info:
                        cmd_release_file_lock(args)

                    assert exc_info.value.code == 0
                    # Verify auto-detected agent ID was used
                    call_kwargs = mock_manager.release_lock.call_args[1]
                    assert call_kwargs["agent_id"] == "agent-auto"

    def test_release_lock_auto_detect_fails(self, capsys):
        """Test lock release fails when auto-detect fails."""
        import os

        args = argparse.Namespace(
            project_root=Path("/test/root"), filepath="test.txt", agent_id=None  # Auto-detect
        )

        with patch.dict(os.environ, {}, clear=True):  # No TMUX_PANE
            with pytest.raises(SystemExit) as exc_info:
                cmd_release_file_lock(args)

            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "Could not auto-detect agent identity" in captured.err


class TestWhoHasLock:
    """Tests for who-has-lock command."""

    def test_who_has_lock_found(self, capsys):
        """Test checking lock when lock exists."""
        args = argparse.Namespace(
            project_root=Path("/test/root"),
            filepath="test.txt",
            json=False,
        )

        mock_lock = Mock()
        mock_lock.agent_id = "agent-1"
        mock_lock.locked_at = 1609459200.0
        mock_lock.reason = "testing"
        mock_lock.age_seconds.return_value = 30.5

        with patch("claudeswarm.cli.LockManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager.who_has_lock.return_value = mock_lock
            mock_manager_class.return_value = mock_manager

            with pytest.raises(SystemExit) as exc_info:
                cmd_who_has_lock(args)

            assert exc_info.value.code == 0
            captured = capsys.readouterr()
            assert "agent-1" in captured.out
            assert "30.5 seconds" in captured.out
            assert "testing" in captured.out

    def test_who_has_lock_not_found(self, capsys):
        """Test checking lock when no lock exists."""
        args = argparse.Namespace(
            project_root=Path("/test/root"),
            filepath="test.txt",
            json=False,
        )

        with patch("claudeswarm.cli.LockManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager.who_has_lock.return_value = None
            mock_manager_class.return_value = mock_manager

            with pytest.raises(SystemExit) as exc_info:
                cmd_who_has_lock(args)

            assert exc_info.value.code == 0
            captured = capsys.readouterr()
            assert "No active lock" in captured.out

    def test_who_has_lock_json_output(self, capsys):
        """Test JSON output for lock query."""
        args = argparse.Namespace(
            project_root=Path("/test/root"),
            filepath="test.txt",
            json=True,
        )

        mock_lock = Mock()
        mock_lock.agent_id = "agent-1"
        mock_lock.locked_at = 1609459200.0
        mock_lock.reason = "testing"
        mock_lock.age_seconds.return_value = 30.5
        mock_lock.to_dict.return_value = {"agent_id": "agent-1", "locked_at": 1609459200.0}

        with patch("claudeswarm.cli.LockManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager.who_has_lock.return_value = mock_lock
            mock_manager_class.return_value = mock_manager

            with pytest.raises(SystemExit) as exc_info:
                cmd_who_has_lock(args)

            assert exc_info.value.code == 0
            captured = capsys.readouterr()
            assert "JSON:" in captured.out


class TestListAllLocks:
    """Tests for list-all-locks command."""

    def test_list_locks_empty(self, capsys):
        """Test listing locks when none exist."""
        args = argparse.Namespace(
            project_root=Path("/test/root"),
            include_stale=False,
            json=False,
        )

        with patch("claudeswarm.cli.LockManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager.list_all_locks.return_value = []
            mock_manager_class.return_value = mock_manager

            with pytest.raises(SystemExit) as exc_info:
                cmd_list_all_locks(args)

            assert exc_info.value.code == 0
            captured = capsys.readouterr()
            assert "No active locks" in captured.out

    def test_list_locks_multiple(self, capsys):
        """Test listing multiple locks."""
        args = argparse.Namespace(
            project_root=Path("/test/root"),
            include_stale=False,
            json=False,
        )

        mock_lock1 = Mock()
        mock_lock1.filepath = "file1.txt"
        mock_lock1.agent_id = "agent-1"
        mock_lock1.locked_at = 1609459200.0
        mock_lock1.reason = "reason1"
        mock_lock1.age_seconds.return_value = 10.0
        mock_lock1.is_stale.return_value = False

        mock_lock2 = Mock()
        mock_lock2.filepath = "file2.txt"
        mock_lock2.agent_id = "agent-2"
        mock_lock2.locked_at = 1609459300.0
        mock_lock2.reason = "reason2"
        mock_lock2.age_seconds.return_value = 20.0
        mock_lock2.is_stale.return_value = False

        with patch("claudeswarm.cli.LockManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager.list_all_locks.return_value = [mock_lock1, mock_lock2]
            mock_manager_class.return_value = mock_manager

            with pytest.raises(SystemExit) as exc_info:
                cmd_list_all_locks(args)

            assert exc_info.value.code == 0
            captured = capsys.readouterr()
            assert "Active locks (2)" in captured.out
            assert "agent-1" in captured.out
            assert "agent-2" in captured.out

    def test_list_locks_with_stale(self, capsys):
        """Test listing locks including stale ones."""
        args = argparse.Namespace(
            project_root=Path("/test/root"),
            include_stale=True,
            json=False,
        )

        mock_lock = Mock()
        mock_lock.filepath = "file1.txt"
        mock_lock.agent_id = "agent-1"
        mock_lock.locked_at = 1609459200.0
        mock_lock.reason = "reason"
        mock_lock.age_seconds.return_value = 1000.0
        mock_lock.is_stale.return_value = True

        with patch("claudeswarm.cli.LockManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager.list_all_locks.return_value = [mock_lock]
            mock_manager_class.return_value = mock_manager

            with pytest.raises(SystemExit) as exc_info:
                cmd_list_all_locks(args)

            assert exc_info.value.code == 0
            captured = capsys.readouterr()
            assert "[STALE]" in captured.out

    def test_list_locks_json_output(self, capsys):
        """Test JSON output for lock listing."""
        args = argparse.Namespace(
            project_root=Path("/test/root"),
            include_stale=False,
            json=True,
        )

        mock_lock = Mock()
        mock_lock.filepath = "file1.txt"
        mock_lock.agent_id = "agent-1"
        mock_lock.locked_at = 1609459200.0
        mock_lock.reason = "reason"
        mock_lock.age_seconds.return_value = 10.0
        mock_lock.is_stale.return_value = False
        mock_lock.to_dict.return_value = {"filepath": "file1.txt", "agent_id": "agent-1"}

        with patch("claudeswarm.cli.LockManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager.list_all_locks.return_value = [mock_lock]
            mock_manager_class.return_value = mock_manager

            with pytest.raises(SystemExit) as exc_info:
                cmd_list_all_locks(args)

            assert exc_info.value.code == 0
            captured = capsys.readouterr()
            assert "JSON:" in captured.out


class TestCleanupStaleLocks:
    """Tests for cleanup-stale-locks command."""

    def test_cleanup_stale_locks_none(self, capsys):
        """Test cleanup when no stale locks exist."""
        args = argparse.Namespace(project_root=Path("/test/root"))

        with patch("claudeswarm.cli.LockManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager.cleanup_stale_locks.return_value = 0
            mock_manager_class.return_value = mock_manager

            with pytest.raises(SystemExit) as exc_info:
                cmd_cleanup_stale_locks(args)

            assert exc_info.value.code == 0
            captured = capsys.readouterr()
            assert "Cleaned up 0 stale lock(s)" in captured.out

    def test_cleanup_stale_locks_multiple(self, capsys):
        """Test cleanup of multiple stale locks."""
        args = argparse.Namespace(project_root=Path("/test/root"))

        with patch("claudeswarm.cli.LockManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager.cleanup_stale_locks.return_value = 3
            mock_manager_class.return_value = mock_manager

            with pytest.raises(SystemExit) as exc_info:
                cmd_cleanup_stale_locks(args)

            assert exc_info.value.code == 0
            captured = capsys.readouterr()
            assert "Cleaned up 3 stale lock(s)" in captured.out


class TestDiscoverAgents:
    """Tests for discover-agents command."""

    def test_discover_agents_basic(self, capsys):
        """Test basic agent discovery."""
        args = argparse.Namespace(
            watch=False,
            json=False,
            stale_threshold=60,
        )

        mock_agent = Mock()
        mock_agent.id = "agent-1"
        mock_agent.pane_index = "0"
        mock_agent.pid = 12345
        mock_agent.status = "active"

        mock_registry = Mock()
        mock_registry.session_name = "test-session"
        mock_registry.updated_at = "2021-01-01T00:00:00"
        mock_registry.agents = [mock_agent]

        with patch("claudeswarm.cli.refresh_registry") as mock_refresh:
            mock_refresh.return_value = mock_registry

            with pytest.raises(SystemExit) as exc_info:
                cmd_discover_agents(args)

            assert exc_info.value.code == 0
            captured = capsys.readouterr()
            assert "Agent Discovery" in captured.out
            assert "agent-1" in captured.out
            assert "test-session" in captured.out

    def test_discover_agents_json(self, capsys):
        """Test agent discovery with JSON output."""
        args = argparse.Namespace(
            watch=False,
            json=True,
            stale_threshold=60,
        )

        mock_registry = Mock()
        mock_registry.to_dict.return_value = {
            "session_name": "test-session",
            "agents": [],
        }

        with patch("claudeswarm.cli.refresh_registry") as mock_refresh:
            mock_refresh.return_value = mock_registry

            with pytest.raises(SystemExit) as exc_info:
                cmd_discover_agents(args)

            assert exc_info.value.code == 0
            captured = capsys.readouterr()
            # Should be valid JSON
            parsed = json.loads(captured.out)
            assert "session_name" in parsed

    def test_discover_agents_watch_mode(self, capsys):
        """Test agent discovery in watch mode."""
        args = argparse.Namespace(
            watch=True,
            json=False,
            stale_threshold=60,
            interval=1,
        )

        mock_registry = Mock()
        mock_registry.session_name = "test-session"
        mock_registry.updated_at = "2021-01-01T00:00:00"
        mock_registry.agents = []

        with patch("claudeswarm.cli.refresh_registry") as mock_refresh:
            mock_refresh.return_value = mock_registry

            with patch("time.sleep") as mock_sleep:
                # Simulate KeyboardInterrupt after first iteration
                mock_sleep.side_effect = KeyboardInterrupt()

                with pytest.raises(SystemExit) as exc_info:
                    cmd_discover_agents(args)

                assert exc_info.value.code == 0
                captured = capsys.readouterr()
                assert "Watching for agents" in captured.out
                assert "Stopped watching" in captured.out

    def test_discover_agents_error_handling(self, capsys):
        """Test error handling in agent discovery."""
        args = argparse.Namespace(
            watch=False,
            json=False,
            stale_threshold=60,
        )

        with patch("claudeswarm.cli.refresh_registry") as mock_refresh:
            mock_refresh.side_effect = RuntimeError("Test error")

            with pytest.raises(SystemExit) as exc_info:
                cmd_discover_agents(args)

            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "Error" in captured.err


class TestListAgents:
    """Tests for list-agents command."""

    def test_list_agents_basic(self, capsys):
        """Test basic agent listing."""
        args = argparse.Namespace(json=False)

        mock_agent = Mock()
        mock_agent.id = "agent-1"
        mock_agent.pane_index = "0"
        mock_agent.pid = 12345
        mock_agent.status = "active"

        with patch("claudeswarm.cli.list_active_agents") as mock_list:
            mock_list.return_value = [mock_agent]

            with pytest.raises(SystemExit) as exc_info:
                cmd_list_agents(args)

            assert exc_info.value.code == 0
            captured = capsys.readouterr()
            assert "Active Agents" in captured.out
            assert "agent-1" in captured.out

    def test_list_agents_empty(self, capsys):
        """Test listing when no agents exist."""
        args = argparse.Namespace(json=False)

        with patch("claudeswarm.cli.list_active_agents") as mock_list:
            mock_list.return_value = []

            with pytest.raises(SystemExit) as exc_info:
                cmd_list_agents(args)

            assert exc_info.value.code == 0
            captured = capsys.readouterr()
            assert "No active agents" in captured.out

    def test_list_agents_json(self, capsys):
        """Test agent listing with JSON output."""
        args = argparse.Namespace(json=True)

        mock_agent = Mock()
        mock_agent.to_dict.return_value = {
            "id": "agent-1",
            "pane_index": "0",
            "pid": 12345,
        }

        with patch("claudeswarm.cli.list_active_agents") as mock_list:
            mock_list.return_value = [mock_agent]

            with pytest.raises(SystemExit) as exc_info:
                cmd_list_agents(args)

            assert exc_info.value.code == 0
            captured = capsys.readouterr()
            parsed = json.loads(captured.out)
            assert len(parsed) == 1
            assert parsed[0]["id"] == "agent-1"


class TestStartMonitoring:
    """Tests for start-monitoring command."""

    def test_start_monitoring_basic(self, capsys):
        """Test basic monitoring start."""
        args = argparse.Namespace(
            filter_type=None,
            filter_agent=None,
            no_tmux=False,
        )

        with patch("claudeswarm.cli.start_monitoring") as mock_start:
            with pytest.raises(SystemExit) as exc_info:
                cmd_start_monitoring(args)

            assert exc_info.value.code == 0
            mock_start.assert_called_once_with(
                filter_type=None,
                filter_agent=None,
                use_tmux=True,
            )

    def test_start_monitoring_with_filters(self, capsys):
        """Test monitoring with filters."""
        args = argparse.Namespace(
            filter_type="BLOCKED",
            filter_agent="agent-1",
            no_tmux=False,
        )

        with patch("claudeswarm.cli.start_monitoring") as mock_start:
            with pytest.raises(SystemExit) as exc_info:
                cmd_start_monitoring(args)

            assert exc_info.value.code == 0
            mock_start.assert_called_once_with(
                filter_type="BLOCKED",
                filter_agent="agent-1",
                use_tmux=True,
            )

    def test_start_monitoring_no_tmux(self, capsys):
        """Test monitoring without tmux."""
        args = argparse.Namespace(
            filter_type=None,
            filter_agent=None,
            no_tmux=True,
        )

        with patch("claudeswarm.cli.start_monitoring") as mock_start:
            with pytest.raises(SystemExit) as exc_info:
                cmd_start_monitoring(args)

            assert exc_info.value.code == 0
            mock_start.assert_called_once_with(
                filter_type=None,
                filter_agent=None,
                use_tmux=False,
            )

    def test_start_monitoring_error(self, capsys):
        """Test monitoring error handling."""
        args = argparse.Namespace(
            filter_type=None,
            filter_agent=None,
            no_tmux=False,
        )

        with patch("claudeswarm.cli.start_monitoring") as mock_start:
            mock_start.side_effect = RuntimeError("Test error")

            with pytest.raises(SystemExit) as exc_info:
                cmd_start_monitoring(args)

            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "Error" in captured.err


class TestMain:
    """Tests for main CLI entry point."""

    def test_main_no_command(self, capsys):
        """Test main with no command shows help."""
        with patch("sys.argv", ["claudeswarm"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

            assert exc_info.value.code == 1

    def test_main_discover_agents(self):
        """Test main with discover-agents command."""
        mock_registry = Mock()
        mock_registry.session_name = "test-session"
        mock_registry.updated_at = "2021-01-01T00:00:00"
        mock_registry.agents = []

        with patch("sys.argv", ["claudeswarm", "discover-agents"]):
            with patch("claudeswarm.cli.refresh_registry") as mock_refresh:
                mock_refresh.return_value = mock_registry

                with pytest.raises(SystemExit) as exc_info:
                    main()

                assert exc_info.value.code == 0

    def test_main_list_agents(self):
        """Test main with list-agents command."""
        with patch("sys.argv", ["claudeswarm", "list-agents"]):
            with patch("claudeswarm.cli.list_active_agents") as mock_list:
                mock_list.return_value = []

                with pytest.raises(SystemExit) as exc_info:
                    main()

                assert exc_info.value.code == 0

    def test_main_acquire_lock(self):
        """Test main with acquire-file-lock command."""
        with patch(
            "sys.argv", ["claudeswarm", "acquire-file-lock", "test.txt", "--agent-id", "agent-1"]
        ):
            with patch("claudeswarm.cli.LockManager") as mock_manager_class:
                mock_manager = Mock()
                mock_manager.acquire_lock.return_value = (True, None)
                mock_manager_class.return_value = mock_manager

                with pytest.raises(SystemExit) as exc_info:
                    main()

                assert exc_info.value.code == 0

    def test_main_release_lock(self):
        """Test main with release-file-lock command."""
        with patch(
            "sys.argv", ["claudeswarm", "release-file-lock", "test.txt", "--agent-id", "agent-1"]
        ):
            with patch("claudeswarm.cli.LockManager") as mock_manager_class:
                mock_manager = Mock()
                mock_manager.release_lock.return_value = True
                mock_manager_class.return_value = mock_manager

                with pytest.raises(SystemExit) as exc_info:
                    main()

                assert exc_info.value.code == 0

    def test_main_who_has_lock(self):
        """Test main with who-has-lock command."""
        with patch("sys.argv", ["claudeswarm", "who-has-lock", "test.txt"]):
            with patch("claudeswarm.cli.LockManager") as mock_manager_class:
                mock_manager = Mock()
                mock_manager.who_has_lock.return_value = None
                mock_manager_class.return_value = mock_manager

                with pytest.raises(SystemExit) as exc_info:
                    main()

                assert exc_info.value.code == 0

    def test_main_list_all_locks(self):
        """Test main with list-all-locks command."""
        with patch("sys.argv", ["claudeswarm", "list-all-locks"]):
            with patch("claudeswarm.cli.LockManager") as mock_manager_class:
                mock_manager = Mock()
                mock_manager.list_all_locks.return_value = []
                mock_manager_class.return_value = mock_manager

                with pytest.raises(SystemExit) as exc_info:
                    main()

                assert exc_info.value.code == 0

    def test_main_cleanup_stale_locks(self):
        """Test main with cleanup-stale-locks command."""
        with patch("sys.argv", ["claudeswarm", "cleanup-stale-locks"]):
            with patch("claudeswarm.cli.LockManager") as mock_manager_class:
                mock_manager = Mock()
                mock_manager.cleanup_stale_locks.return_value = 0
                mock_manager_class.return_value = mock_manager

                with pytest.raises(SystemExit) as exc_info:
                    main()

                assert exc_info.value.code == 0

    def test_main_start_monitoring(self):
        """Test main with start-monitoring command."""
        with patch("sys.argv", ["claudeswarm", "start-monitoring"]):
            with patch("claudeswarm.cli.start_monitoring"):
                with pytest.raises(SystemExit) as exc_info:
                    main()

                assert exc_info.value.code == 0


class TestPrintHelp:
    """Tests for print_help function."""

    def test_print_help_output(self, capsys):
        """Test that help output is generated."""
        print_help()
        captured = capsys.readouterr()
        assert "Claude Swarm" in captured.out
        assert "discover-agents" in captured.out
        assert "Commands:" in captured.out


class TestPrintVersion:
    """Tests for print_version function."""

    def test_print_version_output(self, capsys):
        """Test that version output is generated."""
        with patch("claudeswarm.__version__", "1.2.3"):
            print_version()
            captured = capsys.readouterr()
            assert "claudeswarm" in captured.out
            assert "1.2.3" in captured.out
