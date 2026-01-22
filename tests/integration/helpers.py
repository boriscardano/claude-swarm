"""Integration test helper utilities for Claude Swarm.

This module provides helper functions and classes for integration testing:
- Mock tmux session creation and management
- Mock Claude Code agent instances
- Message delivery verification
- Lock state verification
- Test cleanup utilities
- Time mocking for stale lock testing
"""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from claudeswarm.discovery import Agent, AgentRegistry, get_registry_path
from claudeswarm.locking import LockManager
from claudeswarm.messaging import Message, MessageType


@dataclass
class MockAgent:
    """Represents a mock agent for testing.

    Attributes:
        id: Agent identifier (e.g., "agent-0")
        pane_index: Mock tmux pane identifier
        pid: Mock process ID
        status: Agent status
        working_dir: Temporary working directory for this agent
    """

    id: str
    pane_index: str
    pid: int
    status: str = "active"
    working_dir: Path | None = None

    def to_agent(self) -> Agent:
        """Convert to a real Agent object."""
        return Agent(
            id=self.id,
            pane_index=self.pane_index,
            pid=self.pid,
            status=self.status,
            last_seen=datetime.now(UTC).isoformat(),
            session_name="test-session",
        )


class IntegrationTestContext:
    """Context manager for integration tests.

    Provides:
    - Temporary working directory
    - Mock agent registry
    - Lock manager
    - Message tracking
    - Automatic cleanup
    """

    def __init__(self, num_agents: int = 3):
        """Initialize test context.

        Args:
            num_agents: Number of mock agents to create
        """
        self.num_agents = num_agents
        self.temp_dir: Path | None = None
        self.agents: list[MockAgent] = []
        self.lock_manager: LockManager | None = None
        self.sent_messages: list[Message] = []
        self.original_cwd: Path | None = None

    def __enter__(self) -> IntegrationTestContext:
        """Set up test context."""
        # Create temporary directory
        self.temp_dir = Path(tempfile.mkdtemp(prefix="claude_swarm_test_"))

        # Save original working directory
        self.original_cwd = Path.cwd()

        # Change to temp directory
        import os

        os.chdir(self.temp_dir)

        # Create mock agents
        for i in range(self.num_agents):
            agent = MockAgent(
                id=f"agent-{i}",
                pane_index=f"test-session:0.{i}",
                pid=10000 + i,
                working_dir=self.temp_dir / f"agent-{i}-workspace",
            )
            agent.working_dir.mkdir(parents=True, exist_ok=True)
            self.agents.append(agent)

        # Create mock agent registry
        self._create_mock_registry()

        # Initialize lock manager
        self.lock_manager = LockManager(project_root=self.temp_dir)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clean up test context."""
        # Reset the global messaging system to clear rate limiters
        import claudeswarm.messaging as messaging_module

        messaging_module._default_messaging_system = None

        # Restore original working directory
        if self.original_cwd:
            import os

            os.chdir(self.original_cwd)

        # Clean up temporary directory
        if self.temp_dir and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def _create_mock_registry(self) -> None:
        """Create a mock agent registry file."""
        registry = AgentRegistry(
            session_name="test-session",
            updated_at=datetime.now(UTC).isoformat(),
            agents=[agent.to_agent() for agent in self.agents],
        )

        registry_path = get_registry_path()
        with open(registry_path, "w") as f:
            json.dump(registry.to_dict(), f, indent=2)

    def get_agent(self, agent_id: str) -> MockAgent | None:
        """Get a mock agent by ID."""
        for agent in self.agents:
            if agent.id == agent_id:
                return agent
        return None

    def create_test_file(self, filepath: str, content: str = "") -> Path:
        """Create a test file in the temp directory.

        Args:
            filepath: Relative path to file
            content: File content

        Returns:
            Path to created file
        """
        file_path = self.temp_dir / filepath
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
        return file_path

    def verify_lock_held(self, filepath: str, agent_id: str) -> bool:
        """Verify that a specific agent holds a lock on a file.

        Args:
            filepath: Path to locked file
            agent_id: Expected lock holder

        Returns:
            True if agent holds the lock, False otherwise
        """
        lock = self.lock_manager.who_has_lock(filepath)
        return lock is not None and lock.agent_id == agent_id

    def verify_no_lock(self, filepath: str) -> bool:
        """Verify that a file is not locked.

        Args:
            filepath: Path to check

        Returns:
            True if file is not locked, False otherwise
        """
        return self.lock_manager.who_has_lock(filepath) is None

    def simulate_agent_crash(self, agent_id: str) -> None:
        """Simulate an agent crash by marking it as stale.

        Args:
            agent_id: ID of agent to crash
        """
        agent = self.get_agent(agent_id)
        if agent:
            agent.status = "stale"
            # Update registry
            self._create_mock_registry()

    def advance_time(self, seconds: int) -> None:
        """Simulate time advancement for stale lock testing.

        This modifies lock timestamps to simulate time passing.

        Args:
            seconds: Number of seconds to advance
        """
        # Get all lock files
        lock_dir = self.temp_dir / ".agent_locks"
        if not lock_dir.exists():
            return

        for lock_file in lock_dir.glob("*.lock"):
            try:
                with open(lock_file) as f:
                    lock_data = json.load(f)

                # Subtract seconds from locked_at timestamp to make it older
                lock_data["locked_at"] = lock_data["locked_at"] - seconds

                with open(lock_file, "w") as f:
                    json.dump(lock_data, f, indent=2)
            except (json.JSONDecodeError, KeyError, OSError):
                pass


@contextmanager
def mock_tmux_environment() -> Generator[dict, None, None]:
    """Context manager that mocks tmux environment for testing.

    Yields:
        Dictionary containing mock tmux state
    """
    mock_state = {
        "panes": [],
        "messages_sent": [],
    }

    def mock_send_to_pane(pane_id: str, message: str) -> bool:
        """Mock tmux send-keys command."""
        mock_state["messages_sent"].append(
            {"pane_id": pane_id, "message": message, "timestamp": datetime.now(UTC).isoformat()}
        )
        return True

    def mock_verify_pane_exists(pane_id: str) -> bool:
        """Mock pane existence check."""
        return pane_id in mock_state["panes"]

    with (
        patch(
            "claudeswarm.messaging.TmuxMessageDelivery.send_to_pane", side_effect=mock_send_to_pane
        ),
        patch(
            "claudeswarm.messaging.TmuxMessageDelivery.verify_pane_exists",
            side_effect=mock_verify_pane_exists,
        ),
    ):
        yield mock_state


def verify_message_delivered(
    messages_sent: list[dict],
    sender_id: str,
    recipient_pane: str,
    msg_type: MessageType,
    content_substring: str | None = None,
) -> bool:
    """Verify that a message was delivered to a specific pane.

    Args:
        messages_sent: List of sent messages from mock_tmux_environment
        sender_id: Expected sender ID
        recipient_pane: Expected recipient pane
        msg_type: Expected message type
        content_substring: Optional substring to check in message content

    Returns:
        True if matching message found, False otherwise
    """
    for msg in messages_sent:
        if msg["pane_id"] != recipient_pane:
            continue

        message_text = msg["message"]

        # Check sender
        if f"[{sender_id}]" not in message_text:
            continue

        # Check message type
        if f"[{msg_type.value}]" not in message_text:
            continue

        # Check content if provided
        if content_substring and content_substring not in message_text:
            continue

        return True

    return False


def verify_message_broadcast(
    messages_sent: list[dict], sender_id: str, expected_recipients: list[str], msg_type: MessageType
) -> bool:
    """Verify that a message was broadcast to all expected recipients.

    Args:
        messages_sent: List of sent messages from mock_tmux_environment
        sender_id: Expected sender ID
        expected_recipients: List of expected recipient pane IDs
        msg_type: Expected message type

    Returns:
        True if message was sent to all recipients, False otherwise
    """
    recipients_found = set()

    for msg in messages_sent:
        message_text = msg["message"]

        # Check if this is the right message
        if f"[{sender_id}]" not in message_text:
            continue
        if f"[{msg_type.value}]" not in message_text:
            continue

        # Add to recipients found
        recipients_found.add(msg["pane_id"])

    # Check if all expected recipients received the message
    return set(expected_recipients).issubset(recipients_found)


def create_mock_message(
    sender_id: str,
    recipient_ids: list[str],
    msg_type: MessageType = MessageType.INFO,
    content: str = "Test message",
) -> Message:
    """Create a mock message for testing.

    Args:
        sender_id: Sender agent ID
        recipient_ids: List of recipient agent IDs
        msg_type: Message type
        content: Message content

    Returns:
        Mock Message object
    """
    return Message(
        sender_id=sender_id,
        timestamp=datetime.now(UTC),
        msg_type=msg_type,
        content=content,
        recipients=recipient_ids,
    )


def wait_for_lock_release(
    lock_manager: LockManager, filepath: str, timeout: float = 5.0, poll_interval: float = 0.1
) -> bool:
    """Wait for a lock to be released.

    Args:
        lock_manager: Lock manager to check
        filepath: Path to check
        timeout: Maximum time to wait in seconds
        poll_interval: How often to check in seconds

    Returns:
        True if lock was released within timeout, False otherwise
    """
    start_time = time.time()

    while time.time() - start_time < timeout:
        if lock_manager.who_has_lock(filepath) is None:
            return True
        time.sleep(poll_interval)

    return False


def assert_lock_state(lock_manager: LockManager, expected_locks: dict[str, str]) -> None:
    """Assert that the lock state matches expectations.

    Args:
        lock_manager: Lock manager to check
        expected_locks: Dict mapping filepath -> expected agent_id

    Raises:
        AssertionError: If lock state doesn't match
    """
    all_locks = lock_manager.list_all_locks()
    actual_locks = {lock.filepath: lock.agent_id for lock in all_locks}

    for filepath, expected_agent in expected_locks.items():
        actual_agent = actual_locks.get(filepath)
        assert actual_agent == expected_agent, (
            f"Lock mismatch for {filepath}: " f"expected {expected_agent}, got {actual_agent}"
        )


def cleanup_test_files(*paths: Path) -> None:
    """Clean up test files and directories.

    Args:
        *paths: Paths to remove
    """
    for path in paths:
        if path.exists():
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
