"""Unit tests for discovery module."""

import json
import subprocess
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest

from claudeswarm.discovery import (
    Agent,
    AgentRegistry,
    discover_agents,
    refresh_registry,
    get_agent_by_id,
    list_active_agents,
    _parse_tmux_panes,
    _is_claude_code_process,
    _generate_agent_id,
    _load_existing_registry,
    _save_registry,
)


class TestAgent:
    """Tests for Agent dataclass."""
    
    def test_agent_creation(self):
        """Test creating an Agent instance."""
        agent = Agent(
            id="agent-0",
            pane_index="main:0.0",
            pid=1234,
            status="active",
            last_seen="2025-11-07T12:00:00+00:00",
            session_name="main"
        )
        
        assert agent.id == "agent-0"
        assert agent.pane_index == "main:0.0"
        assert agent.pid == 1234
        assert agent.status == "active"
    
    def test_agent_to_dict(self):
        """Test converting Agent to dictionary."""
        agent = Agent(
            id="agent-0",
            pane_index="main:0.0",
            pid=1234,
            status="active",
            last_seen="2025-11-07T12:00:00+00:00",
            session_name="main"
        )
        
        data = agent.to_dict()
        assert data["id"] == "agent-0"
        assert data["pane_index"] == "main:0.0"
        assert data["pid"] == 1234
    
    def test_agent_from_dict(self):
        """Test creating Agent from dictionary."""
        data = {
            "id": "agent-0",
            "pane_index": "main:0.0",
            "pid": 1234,
            "status": "active",
            "last_seen": "2025-11-07T12:00:00+00:00",
            "session_name": "main"
        }
        
        agent = Agent.from_dict(data)
        assert agent.id == "agent-0"
        assert agent.pid == 1234


class TestAgentRegistry:
    """Tests for AgentRegistry dataclass."""
    
    def test_registry_creation(self):
        """Test creating an AgentRegistry instance."""
        agents = [
            Agent("agent-0", "main:0.0", 1234, "active", "2025-11-07T12:00:00+00:00", "main"),
            Agent("agent-1", "main:0.1", 1235, "active", "2025-11-07T12:00:00+00:00", "main"),
        ]
        
        registry = AgentRegistry(
            session_name="main",
            updated_at="2025-11-07T12:00:00+00:00",
            agents=agents
        )
        
        assert registry.session_name == "main"
        assert len(registry.agents) == 2
    
    def test_registry_to_dict(self):
        """Test converting AgentRegistry to dictionary."""
        agents = [
            Agent("agent-0", "main:0.0", 1234, "active", "2025-11-07T12:00:00+00:00", "main"),
        ]
        
        registry = AgentRegistry(
            session_name="main",
            updated_at="2025-11-07T12:00:00+00:00",
            agents=agents
        )
        
        data = registry.to_dict()
        assert data["session_name"] == "main"
        assert len(data["agents"]) == 1
        assert data["agents"][0]["id"] == "agent-0"
    
    def test_registry_from_dict(self):
        """Test creating AgentRegistry from dictionary."""
        data = {
            "session_name": "main",
            "updated_at": "2025-11-07T12:00:00+00:00",
            "agents": [
                {
                    "id": "agent-0",
                    "pane_index": "main:0.0",
                    "pid": 1234,
                    "status": "active",
                    "last_seen": "2025-11-07T12:00:00+00:00",
                    "session_name": "main"
                }
            ]
        }
        
        registry = AgentRegistry.from_dict(data)
        assert registry.session_name == "main"
        assert len(registry.agents) == 1
        assert registry.agents[0].id == "agent-0"


class TestTmuxParsing:
    """Tests for tmux output parsing."""
    
    @patch("subprocess.run")
    def test_parse_tmux_panes_success(self, mock_run):
        """Test successful parsing of tmux panes."""
        mock_run.return_value = MagicMock(
            stdout="main:0.0|1234|claude\nmain:0.1|1235|bash\nmain:0.2|1236|claude-code\n",
            stderr="",
            returncode=0
        )
        
        panes = _parse_tmux_panes()
        
        assert len(panes) == 3
        assert panes[0]["pane_index"] == "main:0.0"
        assert panes[0]["pid"] == 1234
        assert panes[0]["command"] == "claude"
        assert panes[0]["session_name"] == "main"
    
    @patch("subprocess.run")
    def test_parse_tmux_panes_no_server(self, mock_run):
        """Test handling of tmux server not running."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, ["tmux"], stderr="no server running on /tmp/tmux-1000/default"
        )
        
        with pytest.raises(RuntimeError, match="tmux server is not running"):
            _parse_tmux_panes()
    
    @patch("subprocess.run")
    def test_parse_tmux_panes_timeout(self, mock_run):
        """Test handling of tmux command timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired(["tmux"], 5)
        
        with pytest.raises(RuntimeError, match="tmux command timed out"):
            _parse_tmux_panes()
    
    @patch("subprocess.run")
    def test_parse_tmux_panes_not_installed(self, mock_run):
        """Test handling of tmux not installed."""
        mock_run.side_effect = FileNotFoundError()
        
        with pytest.raises(RuntimeError, match="tmux is not installed"):
            _parse_tmux_panes()
    
    @patch("subprocess.run")
    def test_parse_tmux_panes_malformed_output(self, mock_run):
        """Test handling of malformed tmux output."""
        mock_run.return_value = MagicMock(
            stdout="invalid|output\nmain:0.0|notanumber|claude\n",
            stderr="",
            returncode=0
        )
        
        panes = _parse_tmux_panes()
        
        # Should skip malformed lines
        assert len(panes) == 0


class TestClaudeCodeDetection:
    """Tests for Claude Code process identification."""
    
    def test_is_claude_code_process_claude(self):
        """Test detection of 'claude' command."""
        assert _is_claude_code_process("claude") is True
        assert _is_claude_code_process("CLAUDE") is True
    
    def test_is_claude_code_process_claude_code(self):
        """Test detection of 'claude-code' command."""
        assert _is_claude_code_process("claude-code") is True
        assert _is_claude_code_process("CLAUDE-CODE") is True
    
    def test_is_claude_code_process_node(self):
        """Test detection of 'node' command (may be Claude Code)."""
        assert _is_claude_code_process("node") is True
    
    def test_is_claude_code_process_negative(self):
        """Test non-Claude Code commands."""
        assert _is_claude_code_process("bash") is False
        assert _is_claude_code_process("vim") is False
        assert _is_claude_code_process("python") is False


class TestAgentIdGeneration:
    """Tests for agent ID generation."""
    
    def test_generate_agent_id_new(self):
        """Test generating ID for new pane."""
        existing = {}
        agent_id = _generate_agent_id("main:0.0", existing)
        assert agent_id == "agent-0"
    
    def test_generate_agent_id_reuse(self):
        """Test reusing existing ID for known pane."""
        existing = {"main:0.0": "agent-5"}
        agent_id = _generate_agent_id("main:0.0", existing)
        assert agent_id == "agent-5"
    
    def test_generate_agent_id_incremental(self):
        """Test generating incremental IDs."""
        existing = {
            "main:0.0": "agent-0",
            "main:0.1": "agent-1",
            "main:0.2": "agent-2"
        }
        agent_id = _generate_agent_id("main:0.3", existing)
        assert agent_id == "agent-3"
    
    def test_generate_agent_id_with_gaps(self):
        """Test ID generation with gaps in sequence."""
        existing = {
            "main:0.0": "agent-0",
            "main:0.1": "agent-5",
        }
        agent_id = _generate_agent_id("main:0.2", existing)
        assert agent_id == "agent-6"


class TestRegistryPersistence:
    """Tests for registry file operations."""
    
    def test_save_and_load_registry(self, tmp_path, monkeypatch):
        """Test saving and loading registry."""
        # Change working directory to temp path
        monkeypatch.chdir(tmp_path)
        
        agents = [
            Agent("agent-0", "main:0.0", 1234, "active", "2025-11-07T12:00:00+00:00", "main"),
        ]
        registry = AgentRegistry(
            session_name="main",
            updated_at="2025-11-07T12:00:00+00:00",
            agents=agents
        )
        
        _save_registry(registry)
        
        loaded = _load_existing_registry()
        assert loaded is not None
        assert loaded.session_name == "main"
        assert len(loaded.agents) == 1
        assert loaded.agents[0].id == "agent-0"
    
    def test_load_registry_not_exists(self, tmp_path, monkeypatch):
        """Test loading registry when file doesn't exist."""
        monkeypatch.chdir(tmp_path)
        
        loaded = _load_existing_registry()
        assert loaded is None
    
    def test_load_registry_invalid_json(self, tmp_path, monkeypatch):
        """Test loading registry with invalid JSON."""
        monkeypatch.chdir(tmp_path)
        
        registry_path = tmp_path / "ACTIVE_AGENTS.json"
        registry_path.write_text("{ invalid json }")
        
        loaded = _load_existing_registry()
        assert loaded is None


class TestDiscoverAgents:
    """Tests for agent discovery functionality."""
    
    @patch("claudeswarm.discovery._parse_tmux_panes")
    @patch("claudeswarm.discovery._load_existing_registry")
    def test_discover_agents_basic(self, mock_load, mock_parse, tmp_path, monkeypatch):
        """Test basic agent discovery."""
        monkeypatch.chdir(tmp_path)
        mock_load.return_value = None
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
                "command": "bash"
            },
            {
                "session_name": "main",
                "pane_index": "main:0.2",
                "pid": 1236,
                "command": "claude-code"
            }
        ]
        
        registry = discover_agents()
        
        assert len(registry.agents) == 2  # Only claude and claude-code
        assert registry.agents[0].id == "agent-0"
        assert registry.agents[1].id == "agent-1"
        assert all(a.status == "active" for a in registry.agents)
    
    @patch("claudeswarm.discovery._parse_tmux_panes")
    @patch("claudeswarm.discovery._load_existing_registry")
    def test_discover_agents_preserve_ids(self, mock_load, mock_parse, tmp_path, monkeypatch):
        """Test that agent IDs are preserved across discoveries."""
        monkeypatch.chdir(tmp_path)
        
        # Existing registry
        existing_agents = [
            Agent("agent-5", "main:0.0", 1234, "active", "2025-11-07T12:00:00+00:00", "main"),
        ]
        mock_load.return_value = AgentRegistry(
            session_name="main",
            updated_at="2025-11-07T12:00:00+00:00",
            agents=existing_agents
        )
        
        # Current panes
        mock_parse.return_value = [
            {
                "session_name": "main",
                "pane_index": "main:0.0",
                "pid": 1234,
                "command": "claude"
            }
        ]
        
        registry = discover_agents()
        
        # Should reuse agent-5
        assert len(registry.agents) == 1
        assert registry.agents[0].id == "agent-5"
    
    @patch("claudeswarm.discovery._parse_tmux_panes")
    @patch("claudeswarm.discovery._load_existing_registry")
    def test_discover_agents_stale_detection(self, mock_load, mock_parse, tmp_path, monkeypatch):
        """Test detection of stale agents."""
        monkeypatch.chdir(tmp_path)
        
        # Old timestamp (2 minutes ago)
        old_time = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
        
        existing_agents = [
            Agent("agent-0", "main:0.0", 1234, "active", old_time, "main"),
            Agent("agent-1", "main:0.1", 1235, "active", old_time, "main"),
        ]
        mock_load.return_value = AgentRegistry(
            session_name="main",
            updated_at=old_time,
            agents=existing_agents
        )
        
        # Only one pane still active
        mock_parse.return_value = [
            {
                "session_name": "main",
                "pane_index": "main:0.0",
                "pid": 1234,
                "command": "claude"
            }
        ]
        
        registry = discover_agents(stale_threshold=60)
        
        # agent-0 active, agent-1 should be removed (too old)
        assert len(registry.agents) == 1
        assert registry.agents[0].id == "agent-0"
        assert registry.agents[0].status == "active"
    
    @patch("claudeswarm.discovery._parse_tmux_panes")
    def test_discover_agents_no_panes(self, mock_parse, tmp_path, monkeypatch):
        """Test discovery with no tmux panes."""
        monkeypatch.chdir(tmp_path)
        mock_parse.return_value = []
        
        registry = discover_agents()
        
        assert len(registry.agents) == 0
        assert registry.session_name == "unknown"


class TestRefreshRegistry:
    """Tests for registry refresh functionality."""
    
    @patch("claudeswarm.discovery.discover_agents")
    @patch("claudeswarm.discovery._save_registry")
    def test_refresh_registry(self, mock_save, mock_discover):
        """Test refreshing registry."""
        agents = [
            Agent("agent-0", "main:0.0", 1234, "active", "2025-11-07T12:00:00+00:00", "main"),
        ]
        mock_registry = AgentRegistry(
            session_name="main",
            updated_at="2025-11-07T12:00:00+00:00",
            agents=agents
        )
        mock_discover.return_value = mock_registry
        
        result = refresh_registry()

        # After config integration, default is None (uses config value)
        mock_discover.assert_called_once_with(stale_threshold=None)
        mock_save.assert_called_once()
        assert result == mock_registry


class TestAgentLookup:
    """Tests for agent lookup functions."""
    
    def test_get_agent_by_id(self, tmp_path, monkeypatch):
        """Test looking up agent by ID."""
        monkeypatch.chdir(tmp_path)
        
        agents = [
            Agent("agent-0", "main:0.0", 1234, "active", "2025-11-07T12:00:00+00:00", "main"),
            Agent("agent-1", "main:0.1", 1235, "active", "2025-11-07T12:00:00+00:00", "main"),
        ]
        registry = AgentRegistry(
            session_name="main",
            updated_at="2025-11-07T12:00:00+00:00",
            agents=agents
        )
        _save_registry(registry)
        
        agent = get_agent_by_id("agent-1")
        assert agent is not None
        assert agent.id == "agent-1"
        assert agent.pid == 1235
    
    def test_get_agent_by_id_not_found(self, tmp_path, monkeypatch):
        """Test looking up non-existent agent."""
        monkeypatch.chdir(tmp_path)
        
        agents = [
            Agent("agent-0", "main:0.0", 1234, "active", "2025-11-07T12:00:00+00:00", "main"),
        ]
        registry = AgentRegistry(
            session_name="main",
            updated_at="2025-11-07T12:00:00+00:00",
            agents=agents
        )
        _save_registry(registry)
        
        agent = get_agent_by_id("agent-99")
        assert agent is None
    
    def test_list_active_agents(self, tmp_path, monkeypatch):
        """Test listing active agents."""
        monkeypatch.chdir(tmp_path)
        
        agents = [
            Agent("agent-0", "main:0.0", 1234, "active", "2025-11-07T12:00:00+00:00", "main"),
            Agent("agent-1", "main:0.1", 1235, "stale", "2025-11-07T12:00:00+00:00", "main"),
            Agent("agent-2", "main:0.2", 1236, "active", "2025-11-07T12:00:00+00:00", "main"),
        ]
        registry = AgentRegistry(
            session_name="main",
            updated_at="2025-11-07T12:00:00+00:00",
            agents=agents
        )
        _save_registry(registry)
        
        active = list_active_agents()
        assert len(active) == 2
        assert all(a.status == "active" for a in active)
        assert {a.id for a in active} == {"agent-0", "agent-2"}
    
    def test_list_active_agents_no_registry(self, tmp_path, monkeypatch):
        """Test listing agents with no registry file."""
        monkeypatch.chdir(tmp_path)
        
        active = list_active_agents()
        assert len(active) == 0
