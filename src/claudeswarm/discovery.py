"""Agent discovery system for Claude Swarm.

This module provides functionality to discover active Claude Code agents running
in tmux panes and maintain a registry of their status.
"""

import json
import subprocess
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict

from .config import get_config
from .utils import atomic_write
from .project import get_active_agents_path


@dataclass
class Agent:
    """Represents a discovered Claude Code agent.
    
    Attributes:
        id: Unique agent identifier (e.g., "agent-0", "agent-1")
        pane_index: tmux pane identifier (format: "session:window.pane")
        pid: Process ID of the Claude Code instance
        status: Current status ("active", "stale", "dead")
        last_seen: Timestamp when agent was last detected
        session_name: Name of the tmux session
    """
    id: str
    pane_index: str
    pid: int
    status: str
    last_seen: str  # ISO 8601 format
    session_name: str

    def to_dict(self) -> Dict:
        """Convert agent to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "Agent":
        """Create Agent from dictionary."""
        return cls(**data)


@dataclass
class AgentRegistry:
    """Registry of all discovered agents.
    
    Attributes:
        session_name: Name of the tmux session being monitored
        updated_at: Timestamp of last registry update
        agents: List of discovered agents
    """
    session_name: str
    updated_at: str  # ISO 8601 format
    agents: List[Agent]

    def to_dict(self) -> Dict:
        """Convert registry to dictionary for JSON serialization."""
        return {
            "session_name": self.session_name,
            "updated_at": self.updated_at,
            "agents": [agent.to_dict() for agent in self.agents]
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "AgentRegistry":
        """Create AgentRegistry from dictionary."""
        agents = [Agent.from_dict(a) for a in data.get("agents", [])]
        return cls(
            session_name=data["session_name"],
            updated_at=data["updated_at"],
            agents=agents
        )


def get_registry_path(project_root: Optional[Path] = None) -> Path:
    """Get the path to the agent registry file.

    Args:
        project_root: Optional project root directory

    Returns:
        Path to ACTIVE_AGENTS.json in project root
    """
    return get_active_agents_path(project_root)


def _parse_tmux_panes() -> List[Dict]:
    """Parse tmux pane information.
    
    Returns:
        List of dictionaries containing pane information:
        - session_name: tmux session name
        - window_index: window number
        - pane_index: pane number
        - pane_pid: process ID
        - command: current command running in pane
        
    Raises:
        RuntimeError: If tmux is not running or command fails
    """
    try:
        # Format string for tmux list-panes output
        format_str = "#{session_name}:#{window_index}.#{pane_index}|#{pane_pid}|#{pane_current_command}"
        
        result = subprocess.run(
            ["tmux", "list-panes", "-a", "-F", format_str],
            capture_output=True,
            text=True,
            check=True,
            timeout=5
        )
        
        panes = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
                
            parts = line.split("|")
            if len(parts) != 3:
                continue
                
            pane_index, pid_str, command = parts
            
            # Parse pane_index (format: "session:window.pane")
            try:
                session_window, pane = pane_index.rsplit(".", 1)
                session_name = session_window.split(":")[0]
            except (ValueError, IndexError):
                continue
            
            try:
                pid = int(pid_str)
            except ValueError:
                continue
                
            panes.append({
                "session_name": session_name,
                "pane_index": pane_index,
                "pid": pid,
                "command": command
            })
        
        return panes
        
    except subprocess.TimeoutExpired:
        raise RuntimeError("tmux command timed out")
    except subprocess.CalledProcessError as e:
        if e.returncode == 1 and "no server running" in e.stderr.lower():
            raise RuntimeError("tmux server is not running")
        raise RuntimeError(f"Failed to list tmux panes: {e.stderr}")
    except FileNotFoundError:
        raise RuntimeError("tmux is not installed or not in PATH")


def _has_claude_child_process(pid: int) -> bool:
    """Check if a PID has any child processes running Claude Code.

    Args:
        pid: Parent process ID to check

    Returns:
        True if any child process is the actual Claude Code binary
    """
    try:
        # Get our own PID to exclude from search
        import os
        our_pid = os.getpid()

        # Use ps to find all child processes
        # Format: PID PPID COMMAND
        result = subprocess.run(
            ["ps", "-A", "-o", "pid,ppid,command"],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode != 0:
            return False

        # Search for processes where PPID matches our PID and command is Claude Code
        for line in result.stdout.strip().split("\n"):
            parts = line.split(None, 2)  # Split into max 3 parts
            if len(parts) < 3:
                continue

            try:
                child_pid = int(parts[0])
                ppid = int(parts[1])
                command = parts[2]

                # Skip our own process and its children
                if child_pid == our_pid:
                    continue

                # Check if this is a child of our target PID
                if ppid == pid:
                    command_lower = command.lower()

                    # Exclude any Python processes running claudeswarm
                    if "python" in command_lower and "claudeswarm" in command_lower:
                        continue

                    # Check for Claude Code specific patterns
                    # Must match the actual claude binary, not tools named "claude*"
                    # Match patterns:
                    # - "claude" (bare command)
                    # - "claude <args>" (command with arguments)
                    # - "/path/to/claude" or "/path/to/claude <args>"
                    # - "claude-code"
                    is_claude_binary = (
                        # Match: bare "claude" or "claude " with args
                        command_lower == "claude" or
                        command_lower.startswith("claude ") or
                        # Match: /path/to/claude
                        "/claude" in command_lower and (
                            command_lower.endswith("/claude") or
                            "/claude " in command_lower
                        ) or
                        # Match: claude-code
                        "claude-code" in command_lower
                    )

                    if is_claude_binary and "claudeswarm" not in command_lower:
                        return True
            except (ValueError, IndexError):
                continue

        return False

    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _get_process_cwd(pid: int) -> Optional[str]:
    """Get the current working directory of a process.

    Args:
        pid: Process ID

    Returns:
        Absolute path to process's working directory, or None if unavailable
    """
    try:
        # On macOS, use lsof to find the cwd
        result = subprocess.run(
            ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
            capture_output=True,
            text=True,
            timeout=2
        )

        if result.returncode == 0:
            # Parse lsof output (format: "npath")
            for line in result.stdout.strip().split("\n"):
                if line.startswith("n"):
                    return line[1:]  # Remove the 'n' prefix

        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        return None


def _is_in_project(pid: int, project_root: Path) -> bool:
    """Check if a process is working within the project directory.

    Args:
        pid: Process ID to check
        project_root: Project root directory path

    Returns:
        True if process's working directory is within project_root
    """
    cwd = _get_process_cwd(pid)
    if not cwd:
        return False

    try:
        cwd_path = Path(cwd).resolve()
        project_path = project_root.resolve()

        # Check if cwd is project_root or a subdirectory of it
        return cwd_path == project_path or project_path in cwd_path.parents
    except (ValueError, OSError):
        return False


def _is_claude_code_process(command: str, pid: int) -> bool:
    """Check if a process appears to be Claude Code.

    First checks if the command itself matches Claude Code patterns.
    If not, searches child processes for Claude Code instances.

    Args:
        command: Command string from tmux pane_current_command
        pid: Process ID of the pane

    Returns:
        True if command or its children match Claude Code patterns
    """
    # Common patterns for Claude Code invocations
    claude_patterns = [
        "claude",
        "claude-code",
        "node",  # Claude Code may run as a Node.js process
    ]

    command_lower = command.lower()

    # First check the pane's current command
    if any(pattern in command_lower for pattern in claude_patterns):
        return True

    # If not found in pane command, check child processes
    return _has_claude_child_process(pid)


def _generate_agent_id(pane_index: str, existing_ids: Dict[str, str]) -> str:
    """Generate a stable agent ID for a pane.
    
    Args:
        pane_index: tmux pane identifier
        existing_ids: Mapping of pane_index to agent_id from previous registry
        
    Returns:
        Agent ID string (e.g., "agent-0", "agent-1")
    """
    # Reuse existing ID if pane was previously discovered
    if pane_index in existing_ids:
        return existing_ids[pane_index]
    
    # Generate new ID based on highest existing ID
    max_id = -1
    for agent_id in existing_ids.values():
        if agent_id.startswith("agent-"):
            try:
                num = int(agent_id.split("-")[1])
                max_id = max(max_id, num)
            except (ValueError, IndexError):
                continue
    
    return f"agent-{max_id + 1}"


def _load_existing_registry() -> Optional[AgentRegistry]:
    """Load existing agent registry from file.
    
    Returns:
        AgentRegistry if file exists and is valid, None otherwise
    """
    registry_path = get_registry_path()
    
    if not registry_path.exists():
        return None
    
    try:
        with open(registry_path, "r") as f:
            data = json.load(f)
        return AgentRegistry.from_dict(data)
    except (json.JSONDecodeError, KeyError, ValueError):
        # Invalid registry file, will be overwritten
        return None


def _save_registry(registry: AgentRegistry) -> None:
    """Save agent registry to file atomically.

    Uses atomic write (temp file + rename) to prevent corruption.

    Args:
        registry: AgentRegistry to save
    """
    registry_path = get_registry_path()

    # Convert registry to JSON string
    content = json.dumps(registry.to_dict(), indent=2)

    # Use atomic_write from utils for consistent, safe writing
    atomic_write(registry_path, content)


def discover_agents(session_name: Optional[str] = None, stale_threshold: Optional[int] = None) -> AgentRegistry:
    """Discover active Claude Code agents in tmux panes.

    Args:
        session_name: Optional tmux session name to filter by (None = all sessions)
        stale_threshold: Seconds after which an agent is considered stale
                        (None = use configured discovery.stale_threshold)

    Returns:
        AgentRegistry containing all discovered agents

    Raises:
        RuntimeError: If tmux is not running or discovery fails
    """
    # Use config default if not specified
    if stale_threshold is None:
        stale_threshold = get_config().discovery.stale_threshold

    current_time = datetime.now(timezone.utc)
    
    # Load existing registry to preserve agent IDs
    existing_registry = _load_existing_registry()
    existing_ids = {}
    existing_agents_map = {}
    
    if existing_registry:
        for agent in existing_registry.agents:
            existing_ids[agent.pane_index] = agent.id
            existing_agents_map[agent.pane_index] = agent
    
    # Discover current panes
    panes = _parse_tmux_panes()
    
    # Filter by session if specified
    if session_name:
        panes = [p for p in panes if p["session_name"] == session_name]
    
    # Get project root for directory filtering
    from .project import get_project_root
    project_root = get_project_root()

    # Identify Claude Code agents
    discovered_agents = []
    active_pane_indices = set()

    for pane in panes:
        if not _is_claude_code_process(pane["command"], pane["pid"]):
            continue

        # Filter by project directory - only include agents working in this project
        if not _is_in_project(pane["pid"], project_root):
            continue

        pane_index = pane["pane_index"]
        active_pane_indices.add(pane_index)
        agent_id = _generate_agent_id(pane_index, existing_ids)

        # Add newly generated ID to existing_ids so next iteration sees it
        existing_ids[pane_index] = agent_id

        agent = Agent(
            id=agent_id,
            pane_index=pane_index,
            pid=pane["pid"],
            status="active",
            last_seen=current_time.isoformat(),
            session_name=pane["session_name"]
        )
        discovered_agents.append(agent)
    
    # Check for stale agents (in registry but not currently active)
    for pane_index, agent in existing_agents_map.items():
        if pane_index not in active_pane_indices:
            # Check if agent is stale
            try:
                last_seen = datetime.fromisoformat(agent.last_seen)
                age_seconds = (current_time - last_seen).total_seconds()
                
                if age_seconds < stale_threshold:
                    # Keep as stale
                    agent.status = "stale"
                    discovered_agents.append(agent)
                # else: agent is too old, don't include (dead)
            except (ValueError, TypeError):
                # Invalid timestamp, skip this agent
                pass
    
    # Determine session name for registry
    if session_name:
        registry_session = session_name
    elif discovered_agents:
        # Use session from first discovered agent
        registry_session = discovered_agents[0].session_name
    else:
        # No agents found, use a default
        registry_session = "unknown"
    
    # Create and save registry
    registry = AgentRegistry(
        session_name=registry_session,
        updated_at=current_time.isoformat(),
        agents=discovered_agents
    )
    
    return registry


def refresh_registry(stale_threshold: Optional[int] = None) -> AgentRegistry:
    """Refresh the agent registry file.

    Discovers agents and saves updated registry to ACTIVE_AGENTS.json.

    Args:
        stale_threshold: Seconds after which an agent is considered stale
                        (None = use configured discovery.stale_threshold)

    Returns:
        Updated AgentRegistry

    Raises:
        RuntimeError: If tmux is not running or discovery fails
    """
    registry = discover_agents(stale_threshold=stale_threshold)
    _save_registry(registry)
    return registry


def get_agent_by_id(agent_id: str) -> Optional[Agent]:
    """Look up an agent by ID from the registry.
    
    Args:
        agent_id: Agent identifier (e.g., "agent-0")
        
    Returns:
        Agent if found, None otherwise
    """
    registry_path = get_registry_path()
    
    if not registry_path.exists():
        return None
    
    try:
        with open(registry_path, "r") as f:
            data = json.load(f)
        registry = AgentRegistry.from_dict(data)
        
        for agent in registry.agents:
            if agent.id == agent_id:
                return agent
        
        return None
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


def list_active_agents() -> List[Agent]:
    """Get list of all active agents from the registry.
    
    Returns:
        List of agents with status "active"
    """
    registry_path = get_registry_path()
    
    if not registry_path.exists():
        return []
    
    try:
        with open(registry_path, "r") as f:
            data = json.load(f)
        registry = AgentRegistry.from_dict(data)
        
        return [agent for agent in registry.agents if agent.status == "active"]
    except (json.JSONDecodeError, KeyError, ValueError):
        return []
