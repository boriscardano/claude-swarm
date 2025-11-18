"""Agent discovery system for Claude Swarm.

This module provides functionality to discover active Claude Code agents running
in tmux panes and maintain a registry of their status.

Platform Support:
    - macOS: Full support using lsof for process CWD detection
    - Linux: Partial support (process CWD detection not yet implemented)
    - Windows: Not supported (requires tmux)

Security Considerations:
    - Uses subprocess calls to tmux, ps, pgrep, and lsof with controlled arguments
    - Process scanning excludes the claudeswarm process itself to prevent self-detection
    - All file I/O uses atomic writes to prevent corruption
    - Registry files are stored in .claudeswarm/ directory

Performance Optimizations:
    - Uses pgrep -P instead of ps -A for child process detection (much faster)
    - Caches process CWD lookups within a single discovery run
    - Forces LC_ALL=C for consistent subprocess output parsing
    - Early termination when Claude is found
    - Limits child process scanning to first 50 processes

Performance Optimizations:
    - Uses pgrep -P instead of ps -A for child process detection (much faster)
    - Caches process CWD lookups within a single discovery run
    - Forces LC_ALL=C for consistent subprocess output parsing
    - Early termination when Claude is found
    - Limits child process scanning to first 50 processes

Limitations:
    - Requires tmux to be installed and running
    - Process CWD detection requires platform-specific tools (lsof on macOS)
    - Agents must be running in tmux panes to be discovered
    - Project filtering only works on platforms with CWD detection support
"""

import json
import logging
import os
import platform
import subprocess
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict

from .config import get_config
from .utils import atomic_write
from .project import get_active_agents_path
from .file_lock import FileLock, FileLockTimeout, FileLockError

# Cache for process CWD lookups within a single discovery run
_cwd_cache: Dict[int, Optional[str]] = {}

# Set up logging for this module
logger = logging.getLogger(__name__)


# Custom exceptions
class DiscoveryError(Exception):
    """Base exception for discovery system errors."""
    pass


class TmuxNotRunningError(DiscoveryError):
    """Raised when tmux is not running or not accessible."""
    pass


class TmuxPermissionError(DiscoveryError):
    """Raised when permission denied accessing tmux."""
    pass


class RegistryLockError(DiscoveryError):
    """Raised when unable to acquire lock on registry file."""
    pass


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
        tmux_pane_id: Internal tmux pane ID (format: "%N") for direct TMUX_PANE matching
    """
    id: str
    pane_index: str
    pid: int
    status: str
    last_seen: str  # ISO 8601 format
    session_name: str
    tmux_pane_id: Optional[str] = None  # Internal %N format for TMUX_PANE env var matching

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


def _clear_cwd_cache() -> None:
    """Clear the CWD cache. Called at the start of each discovery run."""
    global _cwd_cache
    _cwd_cache = {}


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
        # Include #{pane_id} for TMUX_PANE env var matching (enables whoami in sandboxed environments)
        format_str = "#{session_name}:#{window_index}.#{pane_index}|#{pane_pid}|#{pane_current_command}|#{pane_id}"

        # Ensure we preserve the TMUX environment variable for proper socket access
        env = os.environ.copy()
        env['LC_ALL'] = 'C'

        # If TMUX is not set, try to detect it
        if 'TMUX' not in env:
            logger.debug("TMUX environment variable not set, attempting to detect tmux socket")

        result = subprocess.run(
            ["tmux", "list-panes", "-a", "-F", format_str],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
            env=env
        )

        panes = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue

            parts = line.split("|")
            if len(parts) != 4:  # Now expecting 4 parts: pane_index, pid, command, pane_id
                continue
                
            pane_index, pid_str, command, tmux_pane_id = parts

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
                "command": command,
                "tmux_pane_id": tmux_pane_id  # Store %N format for TMUX_PANE matching
            })
        
        return panes
        
    except subprocess.TimeoutExpired as e:
        raise TmuxNotRunningError("Tmux command timed out (>5s). Tmux may be unresponsive.") from e
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.lower() if e.stderr else ""
        if e.returncode == 1 and "no server running" in stderr:
            raise TmuxNotRunningError(
                "Tmux server is not running. Start tmux first with 'tmux' or 'tmux new-session'."
            ) from e
        elif "operation not permitted" in stderr or "permission denied" in stderr:
            # This can happen when running from child processes or in restricted environments
            logger.warning(f"Permission error accessing tmux: {e.stderr}")
            raise TmuxPermissionError(
                "Permission denied accessing tmux socket. "
                "This can happen when running from child processes or sandboxed environments. "
                "Try running the command directly in a tmux pane instead of through a subprocess."
            ) from e
        elif "no such file" in stderr or "socket" in stderr:
            raise TmuxNotRunningError(
                f"Tmux socket not found or inaccessible: {e.stderr}. "
                "The tmux server may have crashed or the socket may be stale."
            ) from e
        raise DiscoveryError(f"Failed to list tmux panes: {e.stderr}") from e
    except FileNotFoundError as e:
        raise TmuxNotRunningError("tmux is not installed or not in PATH") from e


def _has_claude_child_process(pid: int) -> bool:
    """Check if a PID has any child processes running Claude Code.

    Uses pgrep for efficient child process detection instead of scanning all processes.
    This is significantly faster than ps -A on systems with many processes.

    Args:
        pid: Parent process ID to check

    Returns:
        True if any child process is the actual Claude Code binary
    """
    try:
        our_pid = os.getpid()

        # Use pgrep -P to only get child processes of the target PID
        # This is MUCH faster than ps -A on systems with many processes
        result = subprocess.run(
            ["pgrep", "-P", str(pid)],
            capture_output=True,
            text=True,
            timeout=2,
            env={**os.environ, 'LC_ALL': 'C'}
        )

        # pgrep returns exit code 1 if no processes found (not an error)
        if result.returncode not in (0, 1):
            return False

        # No child processes found
        if not result.stdout.strip():
            return False

        # Get command line for each child process using ps
        child_pids = result.stdout.strip().split("\n")

        # Early termination: limit to first 50 child processes to avoid hanging
        for child_pid_str in child_pids[:50]:
            try:
                child_pid = int(child_pid_str)

                # Skip our own process
                if child_pid == our_pid:
                    continue

                # Get command for this specific PID using ps
                ps_result = subprocess.run(
                    ["ps", "-p", str(child_pid), "-o", "command="],
                    capture_output=True,
                    text=True,
                    timeout=1,
                    env={**os.environ, 'LC_ALL': 'C'}
                )

                if ps_result.returncode != 0:
                    continue

                command = ps_result.stdout.strip()
                if not command:
                    continue

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
                    return True  # Early exit when Claude is found

            except (ValueError, IndexError):
                continue

        return False

    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _get_process_cwd(pid: int) -> Optional[str]:
    """Get the current working directory of a process.

    This function provides cross-platform support for retrieving a process's
    current working directory:
    - Linux: Uses /proc/{pid}/cwd symlink (fast and reliable)
    - macOS: Uses lsof command (requires lsof to be installed)
    - Windows: Not supported, returns None

    Platform Support:
        - Linux: Full support via /proc filesystem
        - macOS: Full support via lsof command
        - Windows: Not supported (would require pywin32 or ctypes)

    Limitations:
        - Requires lsof to be installed on macOS
        - May fail if process has terminated or doesn't have a CWD
        - Requires sufficient permissions to query process information
        - 0.5-second timeout on macOS to prevent blocking on slow systems

    Edge Cases:
        - Returns None if platform is Windows or unsupported
        - Returns None if PID is invalid or out of range
        - Returns None if lsof is not installed on macOS
        - Returns None if lsof command times out (> 0.5 seconds)
        - Returns None if process has no current working directory
        - Returns None if permission denied accessing process info

    Example:
        >>> cwd = _get_process_cwd(12345)
        >>> if cwd:
        ...     print(f"Process working directory: {cwd}")
        ... else:
        ...     print("Could not determine process CWD")

    Args:
        pid: Process ID (must be a positive integer)

    Returns:
        Absolute path to process's working directory, or None if unavailable

    Raises:
        ValueError: If pid is not a positive integer
    """
    # Check cache first
    if pid in _cwd_cache:
        return _cwd_cache[pid]

    # Input validation
    if not isinstance(pid, int) or pid <= 0:
        raise ValueError(f"PID must be a positive integer, got: {pid}")

    # Check for valid PID range (system-dependent, but general sanity check)
    # Most systems have a maximum PID value, typically 32768 or higher
    # We use a conservative upper bound of 2^22 (4194304)
    MAX_PID = 4194304
    if pid > MAX_PID:
        logger.warning(f"PID {pid} exceeds reasonable maximum ({MAX_PID})")
        _cwd_cache[pid] = None
        return None

    system = platform.system()
    logger.debug(f"Getting CWD for PID {pid} on platform: {system}")

    cwd = None
    if system == "Linux":
        cwd = _get_process_cwd_linux(pid)
    elif system == "Darwin":  # macOS
        cwd = _get_process_cwd_macos(pid)
    elif system == "Windows":
        # Windows is not currently supported for CWD detection
        # Would require pywin32 or ctypes with Windows API calls
        logger.debug(f"Windows platform detected - CWD detection not supported for PID {pid}")
        cwd = None
    else:
        logger.warning(f"Unsupported platform '{system}' for CWD detection")
        cwd = None

    # Cache the result (even if None)
    _cwd_cache[pid] = cwd
    return cwd


def _get_process_cwd_linux(pid: int) -> Optional[str]:
    """Get process CWD on Linux using /proc filesystem.

    Args:
        pid: Process ID

    Returns:
        Absolute path to process's working directory, or None if unavailable
    """
    try:
        # On Linux, /proc/{pid}/cwd is a symlink to the process's CWD
        proc_cwd = Path(f"/proc/{pid}/cwd")

        if not proc_cwd.exists():
            logger.debug(f"Process {pid} does not exist (no /proc/{pid}/cwd)")
            return None

        # Resolve the symlink to get the actual path
        cwd = proc_cwd.resolve(strict=True)
        logger.debug(f"PID {pid} CWD: {cwd}")
        return str(cwd)

    except PermissionError:
        logger.debug(f"Permission denied accessing /proc/{pid}/cwd")
        return None
    except FileNotFoundError:
        logger.debug(f"Process {pid} not found or terminated")
        return None
    except OSError as e:
        logger.debug(f"OS error reading /proc/{pid}/cwd: {e}")
        return None


def _get_process_cwd_macos(pid: int) -> Optional[str]:
    """Get process CWD on macOS using lsof command.

    Args:
        pid: Process ID

    Returns:
        Absolute path to process's working directory, or None if unavailable
    """
    try:
        # On macOS, use lsof to find the cwd
        # -a: AND the selection criteria
        # -p: select by PID
        # -d cwd: select the current working directory
        # -Fn: output in parseable format with names only
        result = subprocess.run(
            ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
            capture_output=True,
            text=True,
            timeout=0.5  # Reduced from 2 seconds for better performance
        )

        if result.returncode == 0:
            # Parse lsof output (format: "npath")
            for line in result.stdout.strip().split("\n"):
                if line.startswith("n"):
                    cwd = line[1:]  # Remove the 'n' prefix
                    logger.debug(f"PID {pid} CWD: {cwd}")
                    return cwd
        else:
            # lsof returns non-zero if process doesn't exist or permission denied
            logger.debug(f"lsof returned code {result.returncode} for PID {pid}")

        return None

    except subprocess.TimeoutExpired:
        logger.warning(f"Timeout getting CWD for PID {pid} using lsof")
        return None
    except FileNotFoundError:
        logger.warning("lsof command not found - install lsof for CWD detection on macOS")
        return None
    except subprocess.SubprocessError as e:
        logger.debug(f"Subprocess error running lsof for PID {pid}: {e}")
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
    """Load existing agent registry from file with file locking.

    Uses shared (read) lock to prevent race conditions when
    multiple processes access the registry simultaneously.

    Returns:
        AgentRegistry if file exists and is valid, None otherwise

    Raises:
        RegistryLockError: If cannot acquire lock within timeout
    """
    registry_path = get_registry_path()

    if not registry_path.exists():
        logger.debug(f"Registry file does not exist: {registry_path}")
        return None

    try:
        # Use shared lock for reading (allows multiple readers)
        with FileLock(registry_path, timeout=5.0, shared=True):
            with open(registry_path, "r") as f:
                data = json.load(f)
            return AgentRegistry.from_dict(data)

    except FileLockTimeout as e:
        raise RegistryLockError(
            f"Timeout acquiring read lock on registry {registry_path}. "
            "Another process may be writing to it."
        ) from e
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON in registry file {registry_path}: {e}")
        # Invalid registry file, will be overwritten
        return None
    except (KeyError, ValueError) as e:
        logger.warning(f"Invalid registry format in {registry_path}: {e}")
        # Invalid registry file, will be overwritten
        return None
    except Exception as e:
        logger.error(f"Unexpected error loading registry: {e}")
        return None


def _save_registry(registry: AgentRegistry) -> None:
    """Save agent registry to file atomically with file locking.

    Uses exclusive (write) lock to prevent race conditions when
    multiple processes try to write to the registry simultaneously.
    Also uses atomic write (temp file + rename) to prevent corruption.

    Args:
        registry: AgentRegistry to save

    Raises:
        RegistryLockError: If cannot acquire exclusive lock within timeout
    """
    registry_path = get_registry_path()

    # Ensure parent directory exists
    registry_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert registry to JSON string
    content = json.dumps(registry.to_dict(), indent=2)

    try:
        # Use exclusive lock for writing (blocks all other access)
        with FileLock(registry_path, timeout=5.0, shared=False):
            # Use atomic_write from utils for consistent, safe writing
            # This writes to a temp file and renames it atomically
            atomic_write(registry_path, content)
            logger.debug(f"Registry saved to {registry_path}")

    except FileLockTimeout as e:
        raise RegistryLockError(
            f"Timeout acquiring write lock on registry {registry_path}. "
            "Another process may be accessing it."
        ) from e
    except Exception as e:
        logger.error(f"Error saving registry to {registry_path}: {e}")
        raise DiscoveryError(f"Failed to save registry: {e}") from e


def discover_agents(session_name: Optional[str] = None, stale_threshold: Optional[int] = None) -> AgentRegistry:
    """Discover active Claude Code agents in tmux panes.

    Args:
        session_name: Optional tmux session name to filter by (None = all sessions)
        stale_threshold: Seconds after which an agent is considered stale
                        (None = use configured discovery.stale_threshold)

    Returns:
        AgentRegistry containing all discovered agents

    Raises:
        TmuxNotRunningError: If tmux is not running or not accessible
        TmuxPermissionError: If permission denied accessing tmux
        RegistryLockError: If cannot acquire lock on registry file
        DiscoveryError: For other discovery-related errors
    """
    # Clear the CWD cache at the start of each discovery run
    _clear_cwd_cache()

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
        # DISABLED: Allow agents from all projects in same tmux session to coordinate
        # if not _is_in_project(pane["pid"], project_root):
        #     continue

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
            session_name=pane["session_name"],
            tmux_pane_id=pane.get("tmux_pane_id")  # Internal %N format for TMUX_PANE matching
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
        TmuxNotRunningError: If tmux is not running or not accessible
        TmuxPermissionError: If permission denied accessing tmux
        RegistryLockError: If cannot acquire lock on registry file
        DiscoveryError: For other discovery-related errors
    """
    registry = discover_agents(stale_threshold=stale_threshold)
    _save_registry(registry)
    logger.info(f"Registry refreshed with {len(registry.agents)} agents")
    return registry


def get_agent_by_id(agent_id: str) -> Optional[Agent]:
    """Look up an agent by ID from the registry with file locking.

    Args:
        agent_id: Agent identifier (e.g., "agent-0")

    Returns:
        Agent if found, None otherwise
    """
    registry_path = get_registry_path()

    if not registry_path.exists():
        logger.debug(f"Registry not found at {registry_path}")
        return None

    try:
        # Use shared lock for reading
        with FileLock(registry_path, timeout=5.0, shared=True):
            with open(registry_path, "r") as f:
                data = json.load(f)
            registry = AgentRegistry.from_dict(data)

        for agent in registry.agents:
            if agent.id == agent_id:
                return agent

        return None

    except FileLockTimeout:
        logger.error(f"Timeout acquiring lock on registry for get_agent_by_id({agent_id})")
        return None
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning(f"Invalid registry format: {e}")
        return None
    except Exception as e:
        logger.error(f"Error reading registry: {e}")
        return None


def list_active_agents() -> List[Agent]:
    """Get list of all active agents from the registry with file locking.

    Returns:
        List of agents with status "active"
    """
    registry_path = get_registry_path()

    if not registry_path.exists():
        logger.debug(f"Registry not found at {registry_path}")
        return []

    try:
        # Use shared lock for reading
        with FileLock(registry_path, timeout=5.0, shared=True):
            with open(registry_path, "r") as f:
                data = json.load(f)
            registry = AgentRegistry.from_dict(data)

        active_agents = [agent for agent in registry.agents if agent.status == "active"]
        logger.debug(f"Found {len(active_agents)} active agents")
        return active_agents

    except FileLockTimeout:
        logger.error("Timeout acquiring lock on registry for list_active_agents()")
        return []
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning(f"Invalid registry format: {e}")
        return []
    except Exception as e:
        logger.error(f"Error reading registry: {e}")
        return []
