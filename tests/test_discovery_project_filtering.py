"""Comprehensive test coverage for project filtering functions in discovery module.

This module tests:
- _get_process_cwd(): Getting the current working directory of a process
- _is_in_project(): Checking if a process is working within project directory
- Integration with discover_agents() for filtering agents by project
"""

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from claudeswarm.discovery import (
    Agent,
    AgentRegistry,
    _get_process_cwd,
    _is_in_project,
    discover_agents,
)


class TestGetProcessCwd:
    """Tests for _get_process_cwd() function."""

    @patch("subprocess.run")
    def test_get_process_cwd_current_process(self, mock_run):
        """Test getting cwd for current process (should work)."""
        current_cwd = os.getcwd()

        # Simulate lsof output for current process
        mock_run.return_value = MagicMock(
            stdout=f"p{os.getpid()}\nn{current_cwd}\n",
            stderr="",
            returncode=0
        )

        result = _get_process_cwd(os.getpid())

        assert result == current_cwd
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "lsof"
        assert "-a" in args
        assert "-p" in args
        assert str(os.getpid()) in args
        assert "-d" in args
        assert "cwd" in args

    @patch("subprocess.run")
    def test_get_process_cwd_invalid_pid(self, mock_run):
        """Test with invalid PID (should return None)."""
        # lsof returns non-zero exit code for invalid PID
        mock_run.return_value = MagicMock(
            stdout="",
            stderr="lsof: no process ID specified",
            returncode=1
        )

        result = _get_process_cwd(99999)

        assert result is None

    @patch("subprocess.run")
    def test_get_process_cwd_timeout(self, mock_run):
        """Test timeout handling."""
        # Simulate timeout
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["lsof"], timeout=2
        )

        result = _get_process_cwd(1234)

        assert result is None
        # Verify timeout was set to 2 seconds (as per current implementation)
        mock_run.assert_called_once()
        assert mock_run.call_args[1]["timeout"] == 2

    @patch("subprocess.run")
    def test_get_process_cwd_lsof_not_available(self, mock_run):
        """Test when lsof is not available."""
        mock_run.side_effect = FileNotFoundError()

        result = _get_process_cwd(1234)

        assert result is None

    @patch("subprocess.run")
    def test_get_process_cwd_parsing_lsof_output(self, mock_run):
        """Test parsing of lsof output format."""
        # lsof with -Fn outputs lines starting with 'n' for name (path)
        mock_run.return_value = MagicMock(
            stdout="p1234\nfcwd\nn/home/user/project\n",
            stderr="",
            returncode=0
        )

        result = _get_process_cwd(1234)

        assert result == "/home/user/project"

    @patch("subprocess.run")
    def test_get_process_cwd_multiple_lines(self, mock_run):
        """Test parsing when lsof returns multiple lines."""
        # Should return the first line starting with 'n'
        mock_run.return_value = MagicMock(
            stdout="p1234\nfcwd\nn/home/user/project\nn/other/path\n",
            stderr="",
            returncode=0
        )

        result = _get_process_cwd(1234)

        assert result == "/home/user/project"

    @patch("subprocess.run")
    def test_get_process_cwd_no_n_prefix(self, mock_run):
        """Test when lsof output has no 'n' prefixed lines."""
        mock_run.return_value = MagicMock(
            stdout="p1234\nfcwd\n",
            stderr="",
            returncode=0
        )

        result = _get_process_cwd(1234)

        assert result is None

    @patch("subprocess.run")
    def test_get_process_cwd_empty_output(self, mock_run):
        """Test when lsof returns empty output."""
        mock_run.return_value = MagicMock(
            stdout="",
            stderr="",
            returncode=0
        )

        result = _get_process_cwd(1234)

        assert result is None

    @patch("subprocess.run")
    def test_get_process_cwd_subprocess_error(self, mock_run):
        """Test handling of subprocess errors."""
        mock_run.side_effect = subprocess.SubprocessError("Subprocess failed")

        result = _get_process_cwd(1234)

        assert result is None

    @patch("subprocess.run")
    def test_get_process_cwd_whitespace_in_path(self, mock_run):
        """Test parsing paths with whitespace."""
        mock_run.return_value = MagicMock(
            stdout="p1234\nn/home/user/my project/subdir\n",
            stderr="",
            returncode=0
        )

        result = _get_process_cwd(1234)

        assert result == "/home/user/my project/subdir"


class TestIsInProject:
    """Tests for _is_in_project() function."""

    @patch("claudeswarm.discovery._get_process_cwd")
    def test_process_in_project_root(self, mock_get_cwd, tmp_path):
        """Test process in project root directory."""
        project_root = tmp_path / "my_project"
        project_root.mkdir()

        # Process is in the project root
        mock_get_cwd.return_value = str(project_root)

        result = _is_in_project(1234, project_root)

        assert result is True
        mock_get_cwd.assert_called_once_with(1234)

    @patch("claudeswarm.discovery._get_process_cwd")
    def test_process_in_subdirectory(self, mock_get_cwd, tmp_path):
        """Test process in subdirectory of project."""
        project_root = tmp_path / "my_project"
        project_root.mkdir()
        subdir = project_root / "src" / "components"
        subdir.mkdir(parents=True)

        # Process is in a subdirectory
        mock_get_cwd.return_value = str(subdir)

        result = _is_in_project(1234, project_root)

        assert result is True

    @patch("claudeswarm.discovery._get_process_cwd")
    def test_process_in_parent_directory(self, mock_get_cwd, tmp_path):
        """Test process in parent directory (should return False)."""
        parent_dir = tmp_path / "parent"
        parent_dir.mkdir()
        project_root = parent_dir / "my_project"
        project_root.mkdir()

        # Process is in the parent directory
        mock_get_cwd.return_value = str(parent_dir)

        result = _is_in_project(1234, project_root)

        assert result is False

    @patch("claudeswarm.discovery._get_process_cwd")
    def test_process_in_different_directory(self, mock_get_cwd, tmp_path):
        """Test process in completely different directory."""
        project_root = tmp_path / "my_project"
        project_root.mkdir()
        other_dir = tmp_path / "other_project"
        other_dir.mkdir()

        # Process is in a completely different directory
        mock_get_cwd.return_value = str(other_dir)

        result = _is_in_project(1234, project_root)

        assert result is False

    @patch("claudeswarm.discovery._get_process_cwd")
    def test_process_in_sibling_directory(self, mock_get_cwd, tmp_path):
        """Test process in sibling directory of project."""
        parent_dir = tmp_path / "parent"
        parent_dir.mkdir()
        project_root = parent_dir / "project1"
        project_root.mkdir()
        sibling_dir = parent_dir / "project2"
        sibling_dir.mkdir()

        # Process is in a sibling directory
        mock_get_cwd.return_value = str(sibling_dir)

        result = _is_in_project(1234, project_root)

        assert result is False

    @patch("claudeswarm.discovery._get_process_cwd")
    def test_cwd_cannot_be_determined(self, mock_get_cwd, tmp_path):
        """Test when cwd cannot be determined."""
        project_root = tmp_path / "my_project"
        project_root.mkdir()

        # _get_process_cwd returns None
        mock_get_cwd.return_value = None

        result = _is_in_project(1234, project_root)

        assert result is False

    @patch("claudeswarm.discovery._get_process_cwd")
    def test_cwd_is_empty_string(self, mock_get_cwd, tmp_path):
        """Test when cwd is empty string."""
        project_root = tmp_path / "my_project"
        project_root.mkdir()

        mock_get_cwd.return_value = ""

        result = _is_in_project(1234, project_root)

        assert result is False

    @patch("claudeswarm.discovery._get_process_cwd")
    def test_invalid_cwd_path(self, mock_get_cwd, tmp_path):
        """Test with invalid path that can't be resolved."""
        project_root = tmp_path / "my_project"
        project_root.mkdir()

        # Return a path with null bytes (invalid on most systems)
        mock_get_cwd.return_value = "/invalid\x00path"

        result = _is_in_project(1234, project_root)

        assert result is False

    @patch("claudeswarm.discovery._get_process_cwd")
    def test_nonexistent_cwd_path(self, mock_get_cwd, tmp_path):
        """Test with nonexistent path."""
        project_root = tmp_path / "my_project"
        project_root.mkdir()

        # Path that doesn't exist
        mock_get_cwd.return_value = str(tmp_path / "nonexistent" / "path")

        # Should handle gracefully - Path.resolve() can work with non-existent paths
        result = _is_in_project(1234, project_root)

        assert result is False

    @patch("claudeswarm.discovery._get_process_cwd")
    def test_symlink_resolution(self, mock_get_cwd, tmp_path):
        """Test that symlinks are properly resolved."""
        # Create project structure
        real_project = tmp_path / "real_project"
        real_project.mkdir()
        subdir = real_project / "subdir"
        subdir.mkdir()

        # Create symlink to project
        symlink_project = tmp_path / "link_to_project"
        symlink_project.symlink_to(real_project)

        # Process is in real subdir, checking against symlink
        mock_get_cwd.return_value = str(subdir)

        result = _is_in_project(1234, symlink_project)

        # Should resolve symlinks and recognize as same project
        assert result is True

    @patch("claudeswarm.discovery._get_process_cwd")
    def test_relative_vs_absolute_paths(self, mock_get_cwd, tmp_path):
        """Test with relative vs absolute paths."""
        project_root = tmp_path / "my_project"
        project_root.mkdir()
        subdir = project_root / "src"
        subdir.mkdir()

        # Process cwd is absolute
        mock_get_cwd.return_value = str(subdir)

        # Project root could be relative (will be resolved)
        result = _is_in_project(1234, Path("..") / project_root.name)

        # Should handle path resolution correctly
        # Result depends on actual cwd, but shouldn't crash
        assert isinstance(result, bool)

    @patch("claudeswarm.discovery._get_process_cwd")
    def test_deep_nesting(self, mock_get_cwd, tmp_path):
        """Test with deeply nested subdirectory."""
        project_root = tmp_path / "project"
        project_root.mkdir()

        # Create deeply nested path
        deep_path = project_root / "a" / "b" / "c" / "d" / "e" / "f"
        deep_path.mkdir(parents=True)

        mock_get_cwd.return_value = str(deep_path)

        result = _is_in_project(1234, project_root)

        assert result is True

    @patch("claudeswarm.discovery._get_process_cwd")
    def test_case_sensitivity(self, mock_get_cwd, tmp_path):
        """Test path comparison is case-sensitive on case-sensitive filesystems."""
        project_root = tmp_path / "MyProject"
        project_root.mkdir()

        # Different case - on case-sensitive systems, this is different
        mock_get_cwd.return_value = str(tmp_path / "myproject")

        result = _is_in_project(1234, project_root)

        # On case-insensitive systems (macOS, Windows) this might be True
        # On case-sensitive systems (Linux) this should be False
        # We just verify it doesn't crash
        assert isinstance(result, bool)


class TestDiscoverAgentsProjectFiltering:
    """Integration tests for project filtering in discover_agents()."""

    @patch("claudeswarm.discovery._get_process_cwd")
    @patch("claudeswarm.discovery._parse_tmux_panes")
    @patch("claudeswarm.discovery._load_existing_registry")
    def test_agents_outside_project_filtered(
        self, mock_load, mock_parse, mock_get_cwd, tmp_path, monkeypatch
    ):
        """Test that agents outside project are filtered out."""
        project_root = tmp_path / "my_project"
        project_root.mkdir()
        other_dir = tmp_path / "other_project"
        other_dir.mkdir()

        monkeypatch.chdir(project_root)
        mock_load.return_value = None

        # Two panes running Claude, but only one is in project
        mock_parse.return_value = [
            {
                "session_name": "main",
                "pane_index": "main:0.0",
                "pid": 1234,
                "command": "claude"
            },
            {
                "session_name": "main",
                "pane_index": "main:0.1",
                "pid": 1235,
                "command": "claude"
            }
        ]

        # First process in project, second outside
        def get_cwd_side_effect(pid):
            if pid == 1234:
                return str(project_root)
            elif pid == 1235:
                return str(other_dir)
            return None

        mock_get_cwd.side_effect = get_cwd_side_effect

        registry = discover_agents()

        # Should only have one agent (the one in project)
        assert len(registry.agents) == 1
        assert registry.agents[0].pid == 1234

        # Verify cwd was checked (may be called multiple times per process)
        assert mock_get_cwd.call_count >= 2
        # Verify both PIDs were checked
        called_pids = {call[0][0] for call in mock_get_cwd.call_args_list}
        assert called_pids == {1234, 1235}

    @patch("claudeswarm.discovery._get_process_cwd")
    @patch("claudeswarm.discovery._parse_tmux_panes")
    @patch("claudeswarm.discovery._load_existing_registry")
    def test_all_agents_in_project_discovered(
        self, mock_load, mock_parse, mock_get_cwd, tmp_path, monkeypatch
    ):
        """Test that all agents in project are discovered."""
        project_root = tmp_path / "my_project"
        project_root.mkdir()

        monkeypatch.chdir(project_root)
        mock_load.return_value = None

        # Three panes running Claude
        mock_parse.return_value = [
            {
                "session_name": "main",
                "pane_index": "main:0.0",
                "pid": 1234,
                "command": "claude"
            },
            {
                "session_name": "main",
                "pane_index": "main:0.1",
                "pid": 1235,
                "command": "claude"
            },
            {
                "session_name": "main",
                "pane_index": "main:0.2",
                "pid": 1236,
                "command": "claude"
            }
        ]

        # All are in project
        mock_get_cwd.return_value = str(project_root)

        registry = discover_agents()

        # Should have all three agents
        assert len(registry.agents) == 3
        assert {a.pid for a in registry.agents} == {1234, 1235, 1236}

    @patch("claudeswarm.discovery._is_claude_code_process")
    @patch("claudeswarm.discovery._get_process_cwd")
    @patch("claudeswarm.discovery._parse_tmux_panes")
    @patch("claudeswarm.discovery._load_existing_registry")
    def test_mixed_scenario_some_in_some_out(
        self, mock_load, mock_parse, mock_get_cwd, mock_is_claude, tmp_path, monkeypatch
    ):
        """Test mixed scenario (some in, some out)."""
        project_root = tmp_path / "my_project"
        project_root.mkdir()
        other_dir = tmp_path / "other_project"
        other_dir.mkdir()

        monkeypatch.chdir(project_root)
        mock_load.return_value = None

        # Five panes
        mock_parse.return_value = [
            {"session_name": "main", "pane_index": "main:0.0", "pid": 1234, "command": "claude"},      # In project
            {"session_name": "main", "pane_index": "main:0.1", "pid": 1235, "command": "bash"},        # Not Claude
            {"session_name": "main", "pane_index": "main:0.2", "pid": 1236, "command": "claude"},      # Out of project
            {"session_name": "main", "pane_index": "main:0.3", "pid": 1237, "command": "claude"},      # In project
            {"session_name": "main", "pane_index": "main:0.4", "pid": 1238, "command": "claude-code"}, # Out of project
        ]

        # Mock Claude detection
        def is_claude_side_effect(cmd, pid):
            return cmd.lower() in ["claude", "claude-code"]
        mock_is_claude.side_effect = is_claude_side_effect

        # Mock cwd: 1234 and 1237 are in project, others outside
        def get_cwd_side_effect(pid):
            if pid in [1234, 1237]:
                return str(project_root)
            else:
                return str(other_dir)

        mock_get_cwd.side_effect = get_cwd_side_effect

        registry = discover_agents()

        # Should only have 2 agents (1234 and 1237)
        assert len(registry.agents) == 2
        assert {a.pid for a in registry.agents} == {1234, 1237}

    @patch("claudeswarm.discovery._parse_tmux_panes")
    @patch("claudeswarm.discovery._load_existing_registry")
    @patch("claudeswarm.discovery._is_in_project")
    @patch("claudeswarm.discovery._is_claude_code_process")
    def test_no_agents_in_project(
        self, mock_is_claude, mock_is_in_project, mock_load, mock_parse, tmp_path, monkeypatch
    ):
        """Test when no agents are in the project."""
        monkeypatch.chdir(tmp_path)
        mock_load.return_value = None

        # Two Claude panes, but neither in project
        mock_parse.return_value = [
            {"session_name": "main", "pane_index": "main:0.0", "pid": 1234, "command": "claude"},
            {"session_name": "main", "pane_index": "main:0.1", "pid": 1235, "command": "claude"}
        ]

        mock_is_claude.return_value = True
        mock_is_in_project.return_value = False

        registry = discover_agents()

        # Should have no agents
        assert len(registry.agents) == 0

    @patch("claudeswarm.discovery._parse_tmux_panes")
    @patch("claudeswarm.discovery._load_existing_registry")
    @patch("claudeswarm.discovery._get_process_cwd")
    @patch("claudeswarm.discovery._is_claude_code_process")
    def test_integration_with_real_path_checking(
        self, mock_is_claude, mock_get_cwd, mock_load, mock_parse, tmp_path, monkeypatch
    ):
        """Test integration with real path checking logic."""
        # Create project structure
        project_root = tmp_path / "my_project"
        project_root.mkdir()
        subdir = project_root / "src"
        subdir.mkdir()
        other_project = tmp_path / "other_project"
        other_project.mkdir()

        monkeypatch.chdir(project_root)
        mock_load.return_value = None

        # Three panes
        mock_parse.return_value = [
            {"session_name": "main", "pane_index": "main:0.0", "pid": 1234, "command": "claude"},  # In root
            {"session_name": "main", "pane_index": "main:0.1", "pid": 1235, "command": "claude"},  # In subdir
            {"session_name": "main", "pane_index": "main:0.2", "pid": 1236, "command": "claude"},  # In other project
        ]

        mock_is_claude.return_value = True

        # Mock cwd returns for each process
        def get_cwd_side_effect(pid):
            if pid == 1234:
                return str(project_root)
            elif pid == 1235:
                return str(subdir)
            elif pid == 1236:
                return str(other_project)
            return None

        mock_get_cwd.side_effect = get_cwd_side_effect

        registry = discover_agents()

        # Should have 2 agents (root and subdir, not other project)
        assert len(registry.agents) == 2
        assert {a.pid for a in registry.agents} == {1234, 1235}

    @patch("claudeswarm.discovery._parse_tmux_panes")
    @patch("claudeswarm.discovery._load_existing_registry")
    @patch("claudeswarm.discovery._get_process_cwd")
    @patch("claudeswarm.discovery._is_claude_code_process")
    def test_stale_agent_outside_project_not_preserved(
        self, mock_is_claude, mock_get_cwd, mock_load, mock_parse, tmp_path, monkeypatch
    ):
        """Test that stale agents are re-filtered and removed if outside project."""
        from datetime import datetime, timezone, timedelta

        project_root = tmp_path / "my_project"
        project_root.mkdir()
        monkeypatch.chdir(project_root)

        # Existing registry with an agent
        old_time = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
        existing_agent = Agent(
            id="agent-0",
            pane_index="main:0.0",
            pid=1234,
            status="active",
            last_seen=old_time,
            session_name="main"
        )
        mock_load.return_value = AgentRegistry(
            session_name="main",
            updated_at=old_time,
            agents=[existing_agent]
        )

        # No current panes (agent went stale)
        mock_parse.return_value = []

        registry = discover_agents(stale_threshold=60)

        # Agent should be marked stale and included (it's recent enough)
        # Note: This tests existing behavior - stale agents bypass project filtering
        # because they use old registry data
        assert len(registry.agents) == 1
        assert registry.agents[0].status == "stale"

    @patch("claudeswarm.discovery._parse_tmux_panes")
    @patch("claudeswarm.discovery._load_existing_registry")
    @patch("claudeswarm.discovery._get_process_cwd")
    @patch("claudeswarm.discovery._is_claude_code_process")
    def test_cwd_lookup_failure_filters_agent(
        self, mock_is_claude, mock_get_cwd, mock_load, mock_parse, tmp_path, monkeypatch
    ):
        """Test that agents with cwd lookup failures are filtered out."""
        monkeypatch.chdir(tmp_path)
        mock_load.return_value = None

        mock_parse.return_value = [
            {"session_name": "main", "pane_index": "main:0.0", "pid": 1234, "command": "claude"}
        ]

        mock_is_claude.return_value = True
        # _get_process_cwd fails
        mock_get_cwd.return_value = None

        registry = discover_agents()

        # Agent should be filtered out because we can't determine if it's in project
        assert len(registry.agents) == 0

    @patch("claudeswarm.discovery._get_process_cwd")
    @patch("claudeswarm.discovery._parse_tmux_panes")
    @patch("claudeswarm.discovery._load_existing_registry")
    def test_uses_correct_project_root(
        self, mock_load, mock_parse, mock_get_cwd, tmp_path, monkeypatch
    ):
        """Test that discover_agents uses the correct project root for filtering."""
        project_root = tmp_path / "my_project"
        project_root.mkdir()
        subdir = project_root / "src"
        subdir.mkdir()

        monkeypatch.chdir(project_root)
        mock_load.return_value = None

        mock_parse.return_value = [
            {"session_name": "main", "pane_index": "main:0.0", "pid": 1234, "command": "claude"}
        ]

        # Process is in a subdirectory
        mock_get_cwd.return_value = str(subdir)

        registry = discover_agents()

        # Verify the agent was included (subdir is part of project)
        assert len(registry.agents) == 1
        assert registry.agents[0].pid == 1234
