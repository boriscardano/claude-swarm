"""Real-time monitoring dashboard for Claude Swarm.

This module provides functionality to:
- Tail agent message logs in real-time
- Filter messages by type, agent, or time range
- Apply color coding to different message types
- Display status sidebar with active agents, locks, pending ACKs
- Run in a dedicated tmux pane
- Auto-refresh status information

The monitoring dashboard provides visibility into agent activity,
helping humans understand coordination patterns and debug issues.

Author: Agent-5
Phase: Phase 2
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from claudeswarm.ack import PendingAck, check_pending_acks
from claudeswarm.discovery import Agent, list_active_agents
from claudeswarm.locking import FileLock, LockManager
from claudeswarm.logging_config import get_logger
from claudeswarm.messaging import Message, MessageType
from claudeswarm.validators import ValidationError, validate_agent_id

__all__ = [
    "MonitoringState",
    "MessageFilter",
    "Monitor",
    "start_monitoring",
    "ColorScheme",
]

# Configure logging
logger = get_logger(__name__)


# ANSI color codes
class ColorScheme:
    """ANSI color codes for terminal output."""

    RED = "\033[91m"
    YELLOW = "\033[93m"
    GREEN = "\033[92m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    GRAY = "\033[90m"
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"


@dataclass
class MonitoringState:
    """Current state of the monitoring dashboard.

    Attributes:
        active_agents: List of currently active agents
        active_locks: List of currently held file locks
        pending_acks: List of messages awaiting acknowledgment
        recent_messages: Ring buffer of recent messages (last 100)
    """

    active_agents: list[Agent]
    active_locks: list[FileLock]
    pending_acks: list[PendingAck]
    recent_messages: deque[Message]


@dataclass
class MessageFilter:
    """Filter criteria for message display.

    Attributes:
        msg_types: If set, only show messages of these types
        agent_ids: If set, only show messages involving these agents
        time_range: If set, only show messages in this time range
    """

    msg_types: set[MessageType] | None = None
    agent_ids: set[str] | None = None
    time_range: tuple[datetime, datetime] | None = None

    def matches(self, message: Message) -> bool:
        """Check if a message matches the filter criteria.

        Optimized for fast filtering of large message volumes.

        Args:
            message: Message to check

        Returns:
            True if message matches all filter criteria
        """
        # Check message type first (fastest check using set membership)
        if self.msg_types is not None and message.msg_type not in self.msg_types:
            return False

        # Check time range early (fast numerical comparison)
        if self.time_range is not None:
            start, end = self.time_range
            if not (start <= message.timestamp <= end):
                return False

        # Check agent IDs last (may involve iteration over recipients)
        if self.agent_ids is not None:
            sender_id = message.sender_id
            # Fast path: check sender first
            if sender_id in self.agent_ids:
                return True
            # Slow path: check recipients (uses optimized set intersection)
            recipients_set = set(message.recipients)
            if not self.agent_ids.intersection(recipients_set):
                return False

        return True


class LogTailer:
    """Handles tailing and parsing of log files.

    Supports context manager protocol for explicit resource management.
    """

    def __init__(self, log_path: Path, max_buffer: int = 100):
        """Initialize log tailer.

        Args:
            log_path: Path to the log file to tail
            max_buffer: Maximum number of messages to keep in buffer
        """
        self.log_path = log_path
        self.max_buffer = max_buffer
        self.position = 0
        self.last_inode = None
        self._file_handle = None
        self._ensure_log_exists()
        self._update_inode()

    def __enter__(self) -> LogTailer:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - cleanup resources."""
        self.cleanup()
        return None

    def cleanup(self) -> None:
        """Clean up any open file handles and reset state."""
        try:
            if self._file_handle is not None:
                self._file_handle.close()
        except Exception:
            pass
        finally:
            self._file_handle = None
        self.position = 0
        self.last_inode = None

    def _ensure_log_exists(self) -> None:
        """Create log file if it doesn't exist."""
        if not self.log_path.exists():
            self.log_path.touch()

    def _update_inode(self) -> None:
        """Update the cached inode number of the log file."""
        if self.log_path.exists():
            try:
                stat_info = self.log_path.stat()
                self.last_inode = stat_info.st_ino
            except OSError:
                self.last_inode = None

    def _detect_log_rotation(self) -> bool:
        """Detect if log file has been rotated.

        Returns:
            True if rotation detected, False otherwise
        """
        if not self.log_path.exists():
            return True

        try:
            stat_info = self.log_path.stat()
            current_size = stat_info.st_size
            current_inode = stat_info.st_ino

            # Check if file size is smaller than our position (rotation detected)
            if current_size < self.position:
                return True

            # Check if inode changed (file was replaced)
            if self.last_inode is not None and current_inode != self.last_inode:
                return True

            return False

        except OSError:
            return True

    def tail_new_lines(self) -> list[str]:
        """Read new lines from the log file since last read.

        Detects log rotation and resets position when needed.

        Returns:
            List of new lines (without newline characters)
        """
        if not self.log_path.exists():
            return []

        # Check for log rotation
        if self._detect_log_rotation():
            self.position = 0
            self._update_inode()

        try:
            with open(self.log_path) as f:
                # Seek to last position
                f.seek(self.position)

                # Read new lines
                new_lines = f.readlines()

                # Update position
                self.position = f.tell()

                # Strip newlines
                return [line.rstrip("\n") for line in new_lines]

        except OSError:
            return []

    def parse_log_entry(self, line: str) -> Message | None:
        """Parse a JSON log entry into a Message object.

        Uses Message.from_log_dict() to handle the log file format which uses
        'sender' instead of 'sender_id'.

        Args:
            line: JSON log entry line from agent_messages.log

        Returns:
            Message object if parsing succeeds, None otherwise
        """
        try:
            data = json.loads(line)

            # Use from_log_dict to handle the log file format
            message = Message.from_log_dict(data)

            return message

        except (json.JSONDecodeError, ValueError, KeyError):
            return None


class Monitor:
    """Main monitoring dashboard implementation.

    Supports context manager protocol for automatic resource cleanup.
    """

    def __init__(
        self,
        log_path: Path = Path("./agent_messages.log"),
        refresh_interval: float = 2.0,
        message_filter: MessageFilter | None = None,
    ):
        """Initialize monitor.

        Args:
            log_path: Path to message log file
            refresh_interval: Seconds between status updates
            message_filter: Optional filter for message display
        """
        self.log_path = log_path
        self.refresh_interval = refresh_interval
        self.message_filter = message_filter or MessageFilter()
        self.tailer = LogTailer(log_path)
        self.lock_manager = LockManager()
        self.recent_messages: deque[Message] = deque(maxlen=100)
        self.running = False

    def __enter__(self) -> Monitor:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - cleanup resources."""
        self.stop()
        return None

    def get_status(self) -> MonitoringState:
        """Get current monitoring state.

        Returns:
            Current MonitoringState with all status information
        """
        # Get active agents
        active_agents = list_active_agents()

        # Get active locks
        active_locks = self.lock_manager.list_all_locks(include_stale=False)

        # Get pending ACKs (may return empty list if not implemented)
        try:
            pending_acks = check_pending_acks()
        except NotImplementedError:
            pending_acks = []

        return MonitoringState(
            active_agents=active_agents,
            active_locks=active_locks,
            pending_acks=pending_acks,
            recent_messages=self.recent_messages,
        )

    def format_with_colors(self, message: Message) -> str:
        """Format a message with ANSI color codes.

        Args:
            message: Message to format

        Returns:
            Colored message string
        """
        # Choose color based on message type
        color = ColorScheme.WHITE

        if message.msg_type == MessageType.BLOCKED:
            color = ColorScheme.RED
        elif message.msg_type in (MessageType.QUESTION, MessageType.ACK):
            color = ColorScheme.YELLOW
        elif message.msg_type == MessageType.COMPLETED:
            color = ColorScheme.GREEN
        elif message.msg_type in (MessageType.INFO, MessageType.REVIEW_REQUEST):
            color = ColorScheme.BLUE
        elif message.msg_type == MessageType.CHALLENGE:
            color = ColorScheme.MAGENTA

        # Format timestamp
        timestamp_str = message.timestamp.strftime("%H:%M:%S")

        # Format message with colors
        formatted = (
            f"{ColorScheme.GRAY}[{timestamp_str}]{ColorScheme.RESET} "
            f"{ColorScheme.BOLD}{message.sender_id}{ColorScheme.RESET} "
            f"{color}[{message.msg_type.value}]{ColorScheme.RESET} "
            f"{message.content}"
        )

        return formatted

    def render_sidebar(self, state: MonitoringState) -> list[str]:
        """Render status sidebar.

        Args:
            state: Current monitoring state

        Returns:
            List of lines for sidebar
        """
        lines = []

        # Header
        lines.append(f"{ColorScheme.BOLD}=== CLAUDE SWARM STATUS ==={ColorScheme.RESET}")
        lines.append("")

        # Active agents
        lines.append(
            f"{ColorScheme.CYAN}Active Agents: {len(state.active_agents)}{ColorScheme.RESET}"
        )
        for agent in state.active_agents:
            lines.append(
                f"  {ColorScheme.GREEN}•{ColorScheme.RESET} {agent.id} ({agent.pane_index})"
            )

        if not state.active_agents:
            lines.append(f"  {ColorScheme.GRAY}No active agents{ColorScheme.RESET}")

        lines.append("")

        # Active locks
        lines.append(
            f"{ColorScheme.MAGENTA}Active Locks: {len(state.active_locks)}{ColorScheme.RESET}"
        )
        for lock in state.active_locks[:5]:  # Show max 5
            age = int(lock.age_seconds())
            lines.append(
                f"  {ColorScheme.MAGENTA}•{ColorScheme.RESET} "
                f"{lock.filepath} ({lock.agent_id}, {age}s)"
            )

        if len(state.active_locks) > 5:
            lines.append(
                f"  {ColorScheme.GRAY}... and {len(state.active_locks) - 5} more{ColorScheme.RESET}"
            )

        if not state.active_locks:
            lines.append(f"  {ColorScheme.GRAY}No active locks{ColorScheme.RESET}")

        lines.append("")

        # Pending ACKs
        lines.append(
            f"{ColorScheme.YELLOW}Pending ACKs: {len(state.pending_acks)}{ColorScheme.RESET}"
        )
        if state.pending_acks:
            for ack in state.pending_acks[:3]:  # Show max 3
                lines.append(
                    f"  {ColorScheme.YELLOW}•{ColorScheme.RESET} "
                    f"{ack.sender_id} → {ack.recipient_id} ({ack.retry_count} retries)"
                )
        else:
            lines.append(f"  {ColorScheme.GRAY}No pending ACKs{ColorScheme.RESET}")

        lines.append("")
        lines.append(
            f"{ColorScheme.GRAY}Updated: {datetime.now().strftime('%H:%M:%S')}{ColorScheme.RESET}"
        )

        return lines

    def clear_screen(self) -> None:
        """Clear the terminal screen."""
        os.system("clear" if os.name != "nt" else "cls")  # nosec B605 - safe hardcoded commands

    def update_display(self) -> None:
        """Update the monitoring display."""
        # Get current state
        state = self.get_status()

        # Clear screen
        self.clear_screen()

        # Render sidebar
        sidebar_lines = self.render_sidebar(state)

        # Print sidebar
        for line in sidebar_lines:
            print(line)

        # Separator
        print(f"\n{ColorScheme.BOLD}{'=' * 80}{ColorScheme.RESET}")
        print(f"{ColorScheme.BOLD}RECENT MESSAGES{ColorScheme.RESET}")
        print(f"{ColorScheme.BOLD}{'=' * 80}{ColorScheme.RESET}\n")

        # Display recent messages (filtered)
        messages_to_show = [msg for msg in self.recent_messages if self.message_filter.matches(msg)]

        # Show last 20 messages
        for message in list(messages_to_show)[-20:]:
            print(self.format_with_colors(message))

        if not messages_to_show:
            print(f"{ColorScheme.GRAY}No messages matching filter criteria{ColorScheme.RESET}")

    def process_new_logs(self) -> None:
        """Process new log entries."""
        new_lines = self.tailer.tail_new_lines()

        for line in new_lines:
            if not line.strip():
                continue

            message = self.tailer.parse_log_entry(line)
            if message:
                self.recent_messages.append(message)

    def run_dashboard(self) -> None:
        """Run the monitoring dashboard main loop.

        Continuously updates display until interrupted.
        """
        self.running = True

        try:
            while self.running:
                # Process new log entries
                self.process_new_logs()

                # Update display
                self.update_display()

                # Sleep until next refresh
                time.sleep(self.refresh_interval)

        except KeyboardInterrupt:
            print(f"\n{ColorScheme.YELLOW}Monitoring stopped{ColorScheme.RESET}")
            sys.exit(0)

        except Exception as e:
            print(f"\n{ColorScheme.RED}Error: {e}{ColorScheme.RESET}", file=sys.stderr)
            sys.exit(1)

    def stop(self) -> None:
        """Stop the monitoring dashboard and cleanup resources."""
        self.running = False
        # Clear message buffer to free memory
        self.recent_messages.clear()
        # Cleanup tailer resources
        if hasattr(self, "tailer") and self.tailer is not None:
            self.tailer.cleanup()


def create_tmux_monitoring_pane(
    pane_name: str = "monitoring", layout: str = "main-vertical"
) -> str | None:
    """Create a dedicated tmux pane for monitoring.

    Args:
        pane_name: Name for the monitoring pane
        layout: Tmux layout to use

    Returns:
        Pane ID if successful, None otherwise
    """
    try:
        # Split current pane vertically
        result = subprocess.run(
            ["tmux", "split-window", "-h", "-P", "-F", "#{pane_id}"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode != 0:
            logger.warning(
                "Failed to create tmux pane: command returned %d, stderr: %s",
                result.returncode,
                result.stderr.strip() if result.stderr else "none",
            )
            return None

        pane_id = result.stdout.strip()

        # Resize the pane to 30% width
        subprocess.run(["tmux", "resize-pane", "-t", pane_id, "-x", "30%"], timeout=5)

        return pane_id

    except subprocess.TimeoutExpired as e:
        logger.warning("Failed to create tmux pane: timeout after %s seconds", e.timeout)
        return None
    except subprocess.CalledProcessError as e:
        logger.warning(
            "Failed to create tmux pane: CalledProcessError (returncode=%d, stderr=%s)",
            e.returncode,
            e.stderr.strip() if e.stderr else "none",
        )
        return None
    except FileNotFoundError:
        logger.warning("Failed to create tmux pane: tmux command not found")
        return None


def start_monitoring(
    filter_type: str | None = None, filter_agent: str | None = None, use_tmux: bool = True
) -> None:
    """Start the monitoring dashboard.

    Uses the backend abstraction for creating monitoring panes when available.
    Falls back to running in the current terminal when the backend doesn't
    support pane creation (e.g., process backend).

    SECURITY NOTE:
    This function handles user-provided filter parameters that are ultimately
    passed to shell commands via tmux send-keys. To prevent command injection:
    1. filter_type is validated against MessageType enum (only fixed values allowed)
    2. filter_agent is validated with validate_agent_id() (alphanumeric, hyphens, underscores only)
    3. Both parameters are escaped with shlex.quote() before shell execution

    Args:
        filter_type: If provided, filter to this message type
        filter_agent: If provided, filter to this agent ID
        use_tmux: Whether to create a dedicated tmux pane (when backend supports it)

    Raises:
        RuntimeError: If tmux is required but not available
    """
    # Build message filter
    msg_filter = MessageFilter()

    if filter_type:
        try:
            msg_filter.msg_types = {MessageType(filter_type)}
        except ValueError:
            print(f"Invalid message type: {filter_type}", file=sys.stderr)
            print(f"Valid types: {', '.join(t.value for t in MessageType)}", file=sys.stderr)
            sys.exit(1)

    if filter_agent:
        # SECURITY: Validate agent_id format to prevent command injection
        try:
            validated_agent = validate_agent_id(filter_agent)
            msg_filter.agent_ids = {validated_agent}
        except ValidationError as e:
            print(f"Invalid agent ID: {e}", file=sys.stderr)
            sys.exit(1)

    # Create monitor
    monitor = Monitor(message_filter=msg_filter)

    # Try to create a dedicated pane via backend
    if use_tmux:
        try:
            from claudeswarm.backend import get_backend

            backend = get_backend()
            pane_id = backend.create_monitoring_pane()
        except Exception:
            pane_id = None

        if pane_id is None and use_tmux:
            # Backend doesn't support pane creation or it failed
            # For tmux backend, try direct tmux as fallback
            try:
                subprocess.run(["tmux", "list-panes"], capture_output=True, timeout=5, check=True)
                pane_id = create_tmux_monitoring_pane()
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass

        if pane_id:
            # Send monitoring command to the new pane
            cmd_parts = [
                "cd",
                shlex.quote(str(Path.cwd())),
                "&&",
                "python",
                "-m",
                "claudeswarm.monitoring",
            ]

            if filter_type:
                try:
                    MessageType(filter_type)
                    cmd_parts.extend(["--filter-type", shlex.quote(filter_type)])
                except ValueError:
                    print(f"Error: Invalid message type: {filter_type}", file=sys.stderr)
                    print(
                        f"Valid types: {', '.join(t.value for t in MessageType)}", file=sys.stderr
                    )
                    sys.exit(1)

            if filter_agent:
                try:
                    validate_agent_id(filter_agent)
                    cmd_parts.extend(["--filter-agent", shlex.quote(filter_agent)])
                except ValidationError as e:
                    print(f"Error: Invalid agent ID: {e}", file=sys.stderr)
                    sys.exit(1)

            cmd = " ".join(cmd_parts)

            subprocess.run(["tmux", "send-keys", "-t", pane_id, cmd, "C-m"], timeout=5)

            print(f"Monitoring dashboard started in tmux pane {pane_id}")
            return
        else:
            print(
                "Note: Running monitoring in current terminal (no pane creation available)",
                file=sys.stderr,
            )

    # Run monitoring in current terminal
    monitor.run_dashboard()


def main() -> None:
    """Main entry point when run as a module."""
    import argparse

    parser = argparse.ArgumentParser(description="Claude Swarm Monitoring Dashboard")
    parser.add_argument(
        "--filter-type", type=str, help="Filter messages by type (e.g., BLOCKED, QUESTION)"
    )
    parser.add_argument("--filter-agent", type=str, help="Filter messages by agent ID")
    parser.add_argument(
        "--no-tmux", action="store_true", help="Run in current terminal instead of tmux pane"
    )

    args = parser.parse_args()

    start_monitoring(
        filter_type=args.filter_type, filter_agent=args.filter_agent, use_tmux=not args.no_tmux
    )


if __name__ == "__main__":
    main()
