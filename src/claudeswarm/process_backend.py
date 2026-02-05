"""Process-based terminal backend for Claude Swarm.

This module provides a terminal-agnostic backend that uses OS-level process
scanning for agent discovery and file-based messaging. It works in any terminal
including Ghostty, iTerm2, Terminal.app, or SSH sessions.

Key design decisions:
- Discovery uses `ps` to find Claude Code processes, then `lsof` for CWD
- Identity uses TTY paths (each terminal split has a unique /dev/ttysNNN)
- Messaging returns False (uses existing file-based hooks system)
- Verification checks PID liveness via os.kill(pid, 0)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .backend import AgentInfo, TerminalBackend
from .logging_config import get_logger

logger = get_logger(__name__)

__all__ = ["ProcessBackend"]

# Timeout for ps command (seconds)
PS_TIMEOUT_SECONDS = 3

# Timeout for lsof CWD detection (seconds)
LSOF_TIMEOUT_SECONDS = 1


def _detect_terminal_name() -> str:
    """Detect the current terminal application name.

    Checks environment variables set by common terminal applications.

    Returns:
        Terminal name string (e.g., "ghostty", "iterm2", "terminal.app", "unknown").
    """
    if os.environ.get("GHOSTTY_RESOURCES_DIR"):
        return "ghostty"

    term_program = os.environ.get("TERM_PROGRAM", "").lower()
    if term_program:
        return term_program

    return "unknown"


def _find_claude_processes() -> list[dict]:
    """Find Claude Code processes using ps.

    Scans running processes for Claude Code instances, excluding the
    current process and claudeswarm tools.

    Returns:
        List of dicts with keys: pid, ppid, tty, command
    """
    our_pid = os.getpid()

    try:
        result = subprocess.run(
            ["ps", "-eo", "pid=,ppid=,tty=,command="],
            capture_output=True,
            text=True,
            timeout=PS_TIMEOUT_SECONDS,
            env={**os.environ, "LC_ALL": "C"},
        )

        if result.returncode != 0:
            logger.debug(f"ps command failed with return code {result.returncode}")
            return []

        processes = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue

            parts = line.strip().split(None, 3)
            if len(parts) < 4:
                continue

            try:
                pid = int(parts[0])
                ppid = int(parts[1])
            except ValueError:
                continue

            tty = parts[2]
            command = parts[3]

            # Skip our own process
            if pid == our_pid:
                continue

            command_lower = command.lower()

            # Skip claudeswarm processes
            if "claudeswarm" in command_lower:
                continue

            # Check if this is a Claude Code process
            is_claude = (
                command_lower == "claude"
                or command_lower.startswith("claude ")
                or command_lower.endswith("/claude")
                or "/claude " in command_lower
                or "claude-code" in command_lower
            )

            if is_claude:
                processes.append(
                    {
                        "pid": pid,
                        "ppid": ppid,
                        "tty": tty if tty != "?" else None,
                        "command": command,
                    }
                )

        return processes

    except subprocess.TimeoutExpired:
        logger.warning("ps command timed out")
        return []
    except FileNotFoundError:
        logger.error("ps command not found")
        return []
    except Exception as e:
        logger.error(f"Error scanning processes: {e}")
        return []


def _get_process_cwd_for_pid(pid: int) -> str | None:
    """Get the current working directory for a process.

    Uses the existing discovery module's CWD detection for cross-platform support.

    Args:
        pid: Process ID.

    Returns:
        CWD path string, or None if unavailable.
    """
    try:
        from .discovery import _get_process_cwd

        return _get_process_cwd(pid)
    except Exception:
        return None


class ProcessBackend(TerminalBackend):
    """Process-based terminal backend.

    Uses OS-level process scanning for discovery and TTY paths for identity.
    Works in any terminal (Ghostty, iTerm2, Terminal.app, SSH, etc.).
    """

    @property
    def name(self) -> str:
        return "process"

    def discover_agents(self, project_root: str | None = None) -> list[AgentInfo]:
        """Discover Claude Code agents by scanning running processes.

        Uses `ps` to find Claude Code processes, then determines their
        working directories to filter by project.

        Args:
            project_root: Optional project root to filter agents by.

        Returns:
            List of AgentInfo for discovered agents.
        """
        claude_processes = _find_claude_processes()
        terminal_name = _detect_terminal_name()

        agents = []
        for proc in claude_processes:
            pid = proc["pid"]
            tty = proc["tty"]
            cwd = _get_process_cwd_for_pid(pid)

            # Filter by project root if specified
            if project_root and cwd:
                try:
                    cwd_path = Path(cwd).resolve()
                    root_path = Path(project_root).resolve()
                    if cwd_path != root_path and root_path not in cwd_path.parents:
                        continue
                except (ValueError, OSError):
                    continue
            elif project_root and not cwd:
                # Can't determine CWD, skip if project filtering is required
                continue

            # Use TTY as identifier, fall back to PID-based identifier
            identifier = tty if tty else f"pid:{pid}"

            agents.append(
                AgentInfo(
                    agent_id="",  # Assigned by discovery module
                    pid=pid,
                    identifier=identifier,
                    session_name=terminal_name,
                    status="active",
                    cwd=cwd,
                    metadata={
                        "tty": tty,
                        "ppid": proc["ppid"],
                        "command": proc["command"],
                    },
                )
            )

        return agents

    def send_message(self, target_identifier: str, message: str) -> bool:
        """Process backend cannot do real-time message delivery.

        Messages are delivered via the existing file-based hooks system
        (agent_messages.log + check-for-messages.sh hook).

        Args:
            target_identifier: Agent identifier (unused).
            message: Message string (unused).

        Returns:
            Always False (file-based fallback is used).
        """
        return False

    def verify_agent(self, identifier: str) -> bool:
        """Verify an agent is still alive.

        For PID-based identifiers, checks process liveness.
        For TTY-based identifiers, checks if the TTY device exists.

        Args:
            identifier: Agent identifier (TTY path or "pid:NNN").

        Returns:
            True if agent appears to be alive.
        """
        if identifier.startswith("pid:"):
            try:
                pid = int(identifier[4:])
                os.kill(pid, 0)
                return True
            except (ValueError, ProcessLookupError, OSError):
                return False

        # TTY-based identifier - check if device exists
        if identifier.startswith("/dev/"):
            return Path(identifier).exists()

        # For bare TTY names (e.g., "ttys005"), check /dev/ prefix
        dev_path = Path(f"/dev/{identifier}")
        if dev_path.exists():
            return True

        return False

    def get_current_agent_identifier(self) -> str | None:
        """Get the TTY path for the current process.

        Each terminal split/tab has a unique TTY device (e.g., /dev/ttys005
        on macOS). This serves the same role as TMUX_PANE.

        Returns:
            TTY device path, or None if not available (e.g., in a pipe).
        """
        try:
            if hasattr(sys.stdout, "fileno"):
                return os.ttyname(sys.stdout.fileno())
        except (OSError, AttributeError):
            pass

        try:
            if hasattr(sys.stdin, "fileno"):
                return os.ttyname(sys.stdin.fileno())
        except (OSError, AttributeError):
            pass

        # Fallback: check /dev/tty
        try:
            fd = os.open("/dev/tty", os.O_RDONLY | os.O_NOCTTY)
            try:
                return os.ttyname(fd)
            finally:
                os.close(fd)
        except OSError:
            pass

        return None

    def create_monitoring_pane(self) -> str | None:
        """Process backend cannot create terminal panes.

        Returns None - monitoring falls through to current terminal
        or web dashboard.

        Returns:
            Always None.
        """
        return None
