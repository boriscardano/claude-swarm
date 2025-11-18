"""
Comprehensive tests for tmux_pane_id discovery functionality.

Tests cover:
- Parsing panes includes tmux_pane_id field
- Handling missing pane_id
- Backwards compatibility with agents without tmux_pane_id
- Matching by tmux_pane_id vs pane_index priority
- Integration with agent discovery

Author: Agent-TestCoverage
"""

import json
import subprocess
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call

import pytest

from claudeswarm.discovery import (
    Agent,
    AgentRegistry,
    _parse_tmux_panes,
    refresh_registry,
    list_active_agents,
)


class TestTmuxPaneIdParsing:
    """Tests for parsing tmux_pane_id from tmux list-panes."""

    @patch('subprocess.run')
    def test_parse_tmux_panes_includes_pane_id(self, mock_run):
        """Test that _parse_tmux_panes includes tmux_pane_id (#{pane_id})."""
        # Mock tmux list-panes output with pane_id
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "test:0.0|12345|bash|%2\ntest:0.1|12346|bash|%3\n"
        mock_run.return_value = mock_result

        panes = _parse_tmux_panes()

        assert len(panes) == 2
        assert panes[0]['pane_id'] == "%2"
        assert panes[1]['pane_id'] == "%3"

    @patch('subprocess.run')
    def test_parse_tmux_panes_pane_id_format(self, mock_run):
        """Test that pane_id has the correct format (%N)."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "test:0.0|12345|bash|%10\n"
        mock_run.return_value = mock_result

        panes = _parse_tmux_panes()

        assert len(panes) == 1
        pane_id = panes[0]['pane_id']
        assert pane_id.startswith('%')
        assert pane_id[1:].isdigit()

    @patch('subprocess.run')
    def test_parse_tmux_panes_multiple_windows(self, mock_run):
        """Test parsing panes across multiple windows with pane_id."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = (
            "session:0.0|12345|bash|%1\n"
            "session:0.1|12346|bash|%2\n"
            "session:1.0|12347|bash|%3\n"
            "session:1.1|12348|bash|%4\n"
        )
        mock_run.return_value = mock_result

        panes = _parse_tmux_panes()

        assert len(panes) == 4
        assert [p['pane_id'] for p in panes] == ["%1", "%2", "%3", "%4"]

    @patch('subprocess.run')
    def test_parse_tmux_panes_empty_output(self, mock_run):
        """Test handling of empty tmux output."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_run.return_value = mock_result

        panes = _parse_tmux_panes()

        assert panes == []

    @patch('subprocess.run')
    def test_parse_tmux_panes_uses_correct_format_string(self, mock_run):
        """Test that tmux list-panes uses the correct format string."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "test:0.0|12345|bash|%2\n"
        mock_run.return_value = mock_result

        _parse_tmux_panes()

        # Verify the format string includes #{pane_id}
        call_args = mock_run.call_args[0][0]
        assert "tmux" in call_args
        assert "list-panes" in call_args
        # The format string should be in the arguments
        format_arg = None
        for i, arg in enumerate(call_args):
            if arg == "-F":
                format_arg = call_args[i + 1]
                break

        assert format_arg is not None
        assert "#{pane_id}" in format_arg


class TestAgentTmuxPaneIdField:
    """Tests for tmux_pane_id field in Agent dataclass."""

    def test_agent_has_tmux_pane_id_field(self):
        """Test that Agent dataclass has tmux_pane_id field."""
        agent = Agent(
            id="agent-1",
            pane_index="test:0.0",
            pid=12345,
            status="active",
            last_seen="2025-11-18T10:00:00Z",
            session_name="test",
            tmux_pane_id="%2"
        )

        assert hasattr(agent, 'tmux_pane_id')
        assert agent.tmux_pane_id == "%2"

    def test_agent_tmux_pane_id_optional(self):
        """Test that tmux_pane_id is optional (for backwards compatibility)."""
        agent = Agent(
            id="agent-1",
            pane_index="test:0.0",
            pid=12345,
            status="active",
            last_seen="2025-11-18T10:00:00Z",
            session_name="test"
            # No tmux_pane_id
        )

        assert hasattr(agent, 'tmux_pane_id')
        assert agent.tmux_pane_id is None

    def test_agent_to_dict_includes_tmux_pane_id(self):
        """Test that Agent.to_dict() includes tmux_pane_id."""
        agent = Agent(
            id="agent-1",
            pane_index="test:0.0",
            pid=12345,
            status="active",
            last_seen="2025-11-18T10:00:00Z",
            session_name="test",
            tmux_pane_id="%2"
        )

        agent_dict = agent.to_dict()

        assert 'tmux_pane_id' in agent_dict
        assert agent_dict['tmux_pane_id'] == "%2"

    def test_agent_to_dict_tmux_pane_id_null(self):
        """Test that to_dict() includes tmux_pane_id even when None."""
        agent = Agent(
            id="agent-1",
            pane_index="test:0.0",
            pid=12345,
            status="active",
            last_seen="2025-11-18T10:00:00Z",
            session_name="test"
        )

        agent_dict = agent.to_dict()

        assert 'tmux_pane_id' in agent_dict
        assert agent_dict['tmux_pane_id'] is None

    def test_agent_from_dict_with_tmux_pane_id(self):
        """Test creating Agent from dict with tmux_pane_id."""
        data = {
            "id": "agent-1",
            "pane_index": "test:0.0",
            "pid": 12345,
            "status": "active",
            "last_seen": "2025-11-18T10:00:00Z",
            "session_name": "test",
            "tmux_pane_id": "%2"
        }

        agent = Agent.from_dict(data)

        assert agent.tmux_pane_id == "%2"

    def test_agent_from_dict_without_tmux_pane_id(self):
        """Test creating Agent from old format dict without tmux_pane_id."""
        data = {
            "id": "agent-1",
            "pane_index": "test:0.0",
            "pid": 12345,
            "status": "active",
            "last_seen": "2025-11-18T10:00:00Z",
            "session_name": "test"
        }

        agent = Agent.from_dict(data)

        assert agent.tmux_pane_id is None


class TestRegistryWithTmuxPaneId:
    """Tests for agent registry persistence with tmux_pane_id."""

    @patch('subprocess.run')
    @patch('claudeswarm.discovery._get_process_cwd')
    @patch('claudeswarm.discovery._find_claude_in_children')
    @patch('claudeswarm.discovery.get_active_agents_path')
    def test_refresh_registry_saves_tmux_pane_id(
        self, mock_get_path, mock_find_claude, mock_get_cwd, mock_run, tmp_path
    ):
        """Test that refresh_registry saves tmux_pane_id to registry."""
        registry_path = tmp_path / "ACTIVE_AGENTS.json"
        mock_get_path.return_value = registry_path

        # Mock tmux list-panes output with pane_id
        mock_tmux_result = Mock()
        mock_tmux_result.returncode = 0
        mock_tmux_result.stdout = "test:0.0|12345|bash|%2\n"

        # Mock tmux display-message to get session name
        mock_session_result = Mock()
        mock_session_result.returncode = 0
        mock_session_result.stdout = "test\n"

        mock_run.side_effect = [mock_tmux_result, mock_session_result]
        mock_get_cwd.return_value = str(tmp_path)
        mock_find_claude.return_value = True

        with patch('claudeswarm.discovery.find_project_root', return_value=tmp_path):
            registry = refresh_registry()

        # Read saved registry
        with open(registry_path, 'r') as f:
            saved_data = json.load(f)

        assert len(saved_data['agents']) == 1
        assert 'tmux_pane_id' in saved_data['agents'][0]
        assert saved_data['agents'][0]['tmux_pane_id'] == "%2"

    @patch('subprocess.run')
    @patch('claudeswarm.discovery._get_process_cwd')
    @patch('claudeswarm.discovery._find_claude_in_children')
    @patch('claudeswarm.discovery.get_active_agents_path')
    def test_refresh_registry_multiple_agents_tmux_pane_id(
        self, mock_get_path, mock_find_claude, mock_get_cwd, mock_run, tmp_path
    ):
        """Test that all agents get unique tmux_pane_id values."""
        registry_path = tmp_path / "ACTIVE_AGENTS.json"
        mock_get_path.return_value = registry_path

        # Mock tmux list-panes output with multiple panes
        mock_tmux_result = Mock()
        mock_tmux_result.returncode = 0
        mock_tmux_result.stdout = (
            "test:0.0|12345|bash|%2\n"
            "test:0.1|12346|bash|%3\n"
            "test:0.2|12347|bash|%4\n"
        )

        mock_session_result = Mock()
        mock_session_result.returncode = 0
        mock_session_result.stdout = "test\n"

        mock_run.side_effect = [mock_tmux_result, mock_session_result]
        mock_get_cwd.return_value = str(tmp_path)
        mock_find_claude.return_value = True

        with patch('claudeswarm.discovery.find_project_root', return_value=tmp_path):
            registry = refresh_registry()

        # Verify all agents have unique pane IDs
        assert len(registry.agents) == 3
        pane_ids = [agent.tmux_pane_id for agent in registry.agents]
        assert pane_ids == ["%2", "%3", "%4"]
        assert len(set(pane_ids)) == 3  # All unique


class TestBackwardsCompatibility:
    """Tests for backwards compatibility with registries without tmux_pane_id."""

    def test_load_registry_without_tmux_pane_id(self, tmp_path):
        """Test loading old registry format without tmux_pane_id."""
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
                    "session_name": "test"
                    # No tmux_pane_id field
                }
            ]
        }

        registry_path = tmp_path / "ACTIVE_AGENTS.json"
        registry_path.write_text(json.dumps(registry_data))

        # Load the registry
        with open(registry_path, 'r') as f:
            data = json.load(f)

        registry = AgentRegistry.from_dict(data)

        assert len(registry.agents) == 1
        assert registry.agents[0].tmux_pane_id is None

    def test_mixed_registry_some_with_tmux_pane_id(self, tmp_path):
        """Test registry with mix of agents (some with, some without tmux_pane_id)."""
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
                    "tmux_pane_id": "%2"  # Has pane ID
                },
                {
                    "id": "agent-2",
                    "pane_index": "test:0.1",
                    "pid": 12346,
                    "status": "active",
                    "last_seen": "2025-11-18T10:00:00Z",
                    "session_name": "test"
                    # No pane ID
                }
            ]
        }

        registry_path = tmp_path / "ACTIVE_AGENTS.json"
        registry_path.write_text(json.dumps(registry_data))

        with open(registry_path, 'r') as f:
            data = json.load(f)

        registry = AgentRegistry.from_dict(data)

        assert len(registry.agents) == 2
        assert registry.agents[0].tmux_pane_id == "%2"
        assert registry.agents[1].tmux_pane_id is None


class TestTmuxPaneIdMatching:
    """Tests for matching agents by tmux_pane_id vs pane_index."""

    def test_whoami_matches_by_tmux_pane_id_first(self, tmp_path):
        """Test that whoami matches by tmux_pane_id before pane_index."""
        # This is tested in test_cli_auto_detect.py
        # Just verify the registry structure supports it
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
                    "tmux_pane_id": "%2"
                },
                {
                    "id": "agent-2",
                    "pane_index": "test:0.1",
                    "pid": 12346,
                    "status": "active",
                    "last_seen": "2025-11-18T10:00:00Z",
                    "session_name": "test",
                    "tmux_pane_id": "%3"
                }
            ]
        }

        registry = AgentRegistry.from_dict(registry_data)

        # Find agent by tmux_pane_id
        target_pane_id = "%2"
        found_agent = None
        for agent in registry.agents:
            if agent.tmux_pane_id == target_pane_id:
                found_agent = agent
                break

        assert found_agent is not None
        assert found_agent.id == "agent-1"

    def test_pane_index_fallback_when_no_tmux_pane_id(self, tmp_path):
        """Test that pane_index matching works when tmux_pane_id is None."""
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
                    "session_name": "test"
                    # No tmux_pane_id
                }
            ]
        }

        registry = AgentRegistry.from_dict(registry_data)

        # Find agent by pane_index
        target_pane_index = "test:0.0"
        found_agent = None
        for agent in registry.agents:
            if agent.pane_index == target_pane_index:
                found_agent = agent
                break

        assert found_agent is not None
        assert found_agent.id == "agent-1"


class TestListActiveAgentsWithTmuxPaneId:
    """Tests for list_active_agents including tmux_pane_id."""

    @patch('claudeswarm.discovery.get_active_agents_path')
    def test_list_active_agents_includes_tmux_pane_id(self, mock_get_path, tmp_path):
        """Test that list_active_agents returns agents with tmux_pane_id."""
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
                    "tmux_pane_id": "%2"
                }
            ]
        }

        registry_path = tmp_path / "ACTIVE_AGENTS.json"
        registry_path.write_text(json.dumps(registry_data))
        mock_get_path.return_value = registry_path

        agents = list_active_agents()

        assert len(agents) == 1
        assert agents[0].tmux_pane_id == "%2"

    @patch('claudeswarm.discovery.get_active_agents_path')
    def test_list_active_agents_handles_missing_tmux_pane_id(
        self, mock_get_path, tmp_path
    ):
        """Test that list_active_agents handles agents without tmux_pane_id."""
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
                    "session_name": "test"
                    # No tmux_pane_id
                }
            ]
        }

        registry_path = tmp_path / "ACTIVE_AGENTS.json"
        registry_path.write_text(json.dumps(registry_data))
        mock_get_path.return_value = registry_path

        agents = list_active_agents()

        assert len(agents) == 1
        assert agents[0].tmux_pane_id is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
