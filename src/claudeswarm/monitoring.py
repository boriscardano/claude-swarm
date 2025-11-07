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
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Set, Tuple

from claudeswarm.ack import PendingAck, check_pending_acks
from claudeswarm.discovery import Agent, list_active_agents
from claudeswarm.locking import FileLock, LockManager
from claudeswarm.messaging import Message, MessageType

__all__ = [
    "MonitoringState",
    "MessageFilter",
    "Monitor",
    "start_monitoring",
    "ColorScheme",
]


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

    msg_types: Optional[Set[MessageType]] = None
    agent_ids: Optional[Set[str]] = None
    time_range: Optional[Tuple[datetime, datetime]] = None

    def matches(self, message: Message) -> bool:
        """Check if a message matches the filter criteria.

        Args:
            message: Message to check

        Returns:
            True if message matches all filter criteria
        """
        # Check message type
        if self.msg_types and message.msg_type not in self.msg_types:
            return False

        # Check agent IDs (sender or recipients)
        if self.agent_ids:
            if message.sender_id not in self.agent_ids:
                # Check if any recipient matches
                if not any(r in self.agent_ids for r in message.recipients):
                    return False

        # Check time range
        if self.time_range:
            start, end = self.time_range
            if not (start <= message.timestamp <= end):
                return False

        return True


class LogTailer:
    """Handles tailing and parsing of log files."""

    def __init__(self, log_path: Path, max_buffer: int = 100):
        """Initialize log tailer.

        Args:
            log_path: Path to the log file to tail
            max_buffer: Maximum number of messages to keep in buffer
        """
        self.log_path = log_path
        self.max_buffer = max_buffer
        self.position = 0
        self._ensure_log_exists()

    def _ensure_log_exists(self) -> None:
        """Create log file if it doesn't exist."""
        if not self.log_path.exists():
            self.log_path.touch()

    def tail_new_lines(self) -> list[str]:
        """Read new lines from the log file since last read.

        Returns:
            List of new lines (without newline characters)
        """
        if not self.log_path.exists():
            return []

        try:
            with open(self.log_path, 'r') as f:
                # Seek to last position
                f.seek(self.position)

                # Read new lines
                new_lines = f.readlines()

                # Update position
                self.position = f.tell()

                # Strip newlines
                return [line.rstrip('\n') for line in new_lines]

        except (OSError, IOError):
            return []

    def parse_log_entry(self, line: str) -> Optional[Message]:
        """Parse a JSON log entry into a Message object.

        Args:
            line: JSON log entry line

        Returns:
            Message object if parsing succeeds, None otherwise
        """
        try:
            data = json.loads(line)

            # Convert to Message format
            message = Message(
                sender_id=data.get('sender', 'unknown'),
                timestamp=datetime.fromisoformat(data.get('timestamp', datetime.now().isoformat())),
                msg_type=MessageType(data.get('msg_type', 'INFO')),
                content=data.get('content', ''),
                recipients=data.get('recipients', []),
                msg_id=data.get('msg_id', '')
            )

            return message

        except (json.JSONDecodeError, ValueError, KeyError):
            return None


class Monitor:
    """Main monitoring dashboard implementation."""

    def __init__(
        self,
        log_path: Path = Path("./agent_messages.log"),
        refresh_interval: float = 2.0,
        message_filter: Optional[MessageFilter] = None
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
            recent_messages=self.recent_messages
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
        timestamp_str = message.timestamp.strftime('%H:%M:%S')

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
        lines.append(f"{ColorScheme.CYAN}Active Agents: {len(state.active_agents)}{ColorScheme.RESET}")
        for agent in state.active_agents:
            lines.append(f"  {ColorScheme.GREEN}•{ColorScheme.RESET} {agent.id} ({agent.pane_index})")

        if not state.active_agents:
            lines.append(f"  {ColorScheme.GRAY}No active agents{ColorScheme.RESET}")

        lines.append("")

        # Active locks
        lines.append(f"{ColorScheme.MAGENTA}Active Locks: {len(state.active_locks)}{ColorScheme.RESET}")
        for lock in state.active_locks[:5]:  # Show max 5
            age = int(lock.age_seconds())
            lines.append(
                f"  {ColorScheme.MAGENTA}•{ColorScheme.RESET} "
                f"{lock.filepath} ({lock.agent_id}, {age}s)"
            )

        if len(state.active_locks) > 5:
            lines.append(f"  {ColorScheme.GRAY}... and {len(state.active_locks) - 5} more{ColorScheme.RESET}")

        if not state.active_locks:
            lines.append(f"  {ColorScheme.GRAY}No active locks{ColorScheme.RESET}")

        lines.append("")

        # Pending ACKs
        lines.append(f"{ColorScheme.YELLOW}Pending ACKs: {len(state.pending_acks)}{ColorScheme.RESET}")
        if state.pending_acks:
            for ack in state.pending_acks[:3]:  # Show max 3
                lines.append(
                    f"  {ColorScheme.YELLOW}•{ColorScheme.RESET} "
                    f"{ack.sender_id} → {ack.recipient_id} ({ack.retry_count} retries)"
                )
        else:
            lines.append(f"  {ColorScheme.GRAY}No pending ACKs{ColorScheme.RESET}")

        lines.append("")
        lines.append(f"{ColorScheme.GRAY}Updated: {datetime.now().strftime('%H:%M:%S')}{ColorScheme.RESET}")

        return lines

    def clear_screen(self) -> None:
        """Clear the terminal screen."""
        os.system('clear' if os.name != 'nt' else 'cls')

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
        messages_to_show = [
            msg for msg in self.recent_messages
            if self.message_filter.matches(msg)
        ]

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
        """Stop the monitoring dashboard."""
        self.running = False


def create_tmux_monitoring_pane(
    pane_name: str = "monitoring",
    layout: str = "main-vertical"
) -> Optional[str]:
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
            ['tmux', 'split-window', '-h', '-P', '-F', '#{pane_id}'],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode != 0:
            return None

        pane_id = result.stdout.strip()

        # Resize the pane to 30% width
        subprocess.run(
            ['tmux', 'resize-pane', '-t', pane_id, '-x', '30%'],
            timeout=5
        )

        return pane_id

    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
        return None


def start_monitoring(
    filter_type: Optional[str] = None,
    filter_agent: Optional[str] = None,
    use_tmux: bool = True
) -> None:
    """Start the monitoring dashboard.

    Args:
        filter_type: If provided, filter to this message type
        filter_agent: If provided, filter to this agent ID
        use_tmux: Whether to create a dedicated tmux pane

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
        msg_filter.agent_ids = {filter_agent}

    # Create monitor
    monitor = Monitor(message_filter=msg_filter)

    # If using tmux, create dedicated pane
    if use_tmux:
        # Check if tmux is available
        try:
            subprocess.run(
                ['tmux', 'list-panes'],
                capture_output=True,
                timeout=5,
                check=True
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError("tmux is not available or not running")

        # Create monitoring pane
        pane_id = create_tmux_monitoring_pane()
        if not pane_id:
            print("Warning: Failed to create tmux pane, running in current terminal", file=sys.stderr)
        else:
            # Send monitoring command to the new pane
            # Build command to run monitoring in the new pane
            cmd = f"cd {Path.cwd()} && python -m claudeswarm.monitoring"

            if filter_type:
                cmd += f" --filter-type {filter_type}"
            if filter_agent:
                cmd += f" --filter-agent {filter_agent}"

            subprocess.run(
                ['tmux', 'send-keys', '-t', pane_id, cmd, 'C-m'],
                timeout=5
            )

            print(f"Monitoring dashboard started in tmux pane {pane_id}")
            return

    # Run monitoring in current terminal
    monitor.run_dashboard()


def main() -> None:
    """Main entry point when run as a module."""
    import argparse

    parser = argparse.ArgumentParser(description="Claude Swarm Monitoring Dashboard")
    parser.add_argument(
        '--filter-type',
        type=str,
        help='Filter messages by type (e.g., BLOCKED, QUESTION)'
    )
    parser.add_argument(
        '--filter-agent',
        type=str,
        help='Filter messages by agent ID'
    )
    parser.add_argument(
        '--no-tmux',
        action='store_true',
        help='Run in current terminal instead of tmux pane'
    )

    args = parser.parse_args()

    start_monitoring(
        filter_type=args.filter_type,
        filter_agent=args.filter_agent,
        use_tmux=not args.no_tmux
    )


if __name__ == '__main__':
    main()
