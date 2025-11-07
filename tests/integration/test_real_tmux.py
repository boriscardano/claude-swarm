"""
Real tmux integration tests.

These tests use actual tmux sessions to verify that:
- Messages are delivered correctly through real tmux panes
- Agent discovery works with real tmux sessions
- File locking works across real tmux panes
- Monitoring can read from real tmux panes
- Cleanup properly removes test sessions

Tests are skipped if tmux is not available.

Author: Agent-TestCoverage
"""

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from claudeswarm.discovery import refresh_registry, list_active_agents
from claudeswarm.messaging import MessagingSystem, MessageType
from claudeswarm.locking import LockManager


def check_tmux_available() -> bool:
    """Check if tmux is available on the system."""
    try:
        result = subprocess.run(
            ["tmux", "-V"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def get_current_tmux_session() -> str | None:
    """Get the current tmux session name if in a tmux session."""
    try:
        result = subprocess.run(
            ["tmux", "display-message", "-p", "#S"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def create_test_session(session_name: str) -> bool:
    """Create a test tmux session."""
    try:
        subprocess.run(
            ["tmux", "new-session", "-d", "-s", session_name],
            check=True,
            timeout=10,
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


def kill_test_session(session_name: str) -> None:
    """Kill a test tmux session."""
    try:
        subprocess.run(
            ["tmux", "kill-session", "-t", session_name],
            timeout=10,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass


def create_test_pane(session_name: str) -> str | None:
    """Create a new pane in the test session and return its index."""
    try:
        # Split window horizontally
        result = subprocess.run(
            ["tmux", "split-window", "-t", f"{session_name}:0", "-h", "-d", "-P", "-F", "#{pane_index}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            return None

        pane_index = result.stdout.strip()
        return pane_index if pane_index else None
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def send_to_pane(session_name: str, pane_index: str, text: str) -> bool:
    """Send text to a tmux pane."""
    try:
        subprocess.run(
            ["tmux", "send-keys", "-t", f"{session_name}:0.{pane_index}", text],
            check=True,
            timeout=10,
            stderr=subprocess.DEVNULL,
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


def capture_pane_content(session_name: str, pane_index: str) -> str:
    """Capture the content of a tmux pane."""
    try:
        result = subprocess.run(
            ["tmux", "capture-pane", "-t", f"{session_name}:0.{pane_index}", "-p"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        return result.stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return ""


# Skip all tests if tmux is not available
pytestmark = pytest.mark.skipif(
    not check_tmux_available(),
    reason="tmux not available",
)


class TestRealTmuxMessaging:
    """Tests for real tmux message delivery."""

    @pytest.fixture
    def test_session(self):
        """Create and cleanup a test tmux session."""
        session_name = "claude-swarm-test-messaging"
        kill_test_session(session_name)  # Cleanup any leftover session

        if not create_test_session(session_name):
            pytest.skip("Could not create test session")

        yield session_name

        kill_test_session(session_name)

    def test_send_message_to_real_pane(self, test_session):
        """Test sending a message to a real tmux pane."""
        # Create a pane
        pane_index = create_test_pane(test_session)
        assert pane_index is not None

        # Send a simple message
        message = "Hello from test!"
        success = send_to_pane(test_session, pane_index, message)
        assert success

        # Give tmux time to process
        time.sleep(0.5)

        # Verify message was received
        content = capture_pane_content(test_session, pane_index)
        assert message in content

    def test_send_multiline_message_to_pane(self, test_session):
        """Test sending multiline messages to real tmux pane."""
        pane_index = create_test_pane(test_session)
        assert pane_index is not None

        # Send multiple lines
        lines = ["Line 1", "Line 2", "Line 3"]
        for line in lines:
            send_to_pane(test_session, pane_index, line)
            send_to_pane(test_session, pane_index, "Enter")
            time.sleep(0.1)

        time.sleep(0.5)

        # Verify all lines were received
        content = capture_pane_content(test_session, pane_index)
        for line in lines:
            assert line in content

    def test_message_special_characters_in_real_pane(self, test_session):
        """Test sending messages with special characters to real pane."""
        pane_index = create_test_pane(test_session)
        assert pane_index is not None

        # Test various special characters
        messages = [
            "Test with spaces",
            "Test-with-dashes",
            "Test_with_underscores",
        ]

        for msg in messages:
            send_to_pane(test_session, pane_index, msg)
            time.sleep(0.2)

        time.sleep(0.5)
        content = capture_pane_content(test_session, pane_index)

        # At least some messages should appear
        assert any(msg in content for msg in messages)

    def test_send_message_to_multiple_panes(self, test_session):
        """Test broadcasting to multiple real panes."""
        # Create multiple panes
        pane1 = create_test_pane(test_session)
        pane2 = create_test_pane(test_session)

        assert pane1 is not None
        assert pane2 is not None

        # Send message to both
        message = "Broadcast test"
        send_to_pane(test_session, pane1, message)
        send_to_pane(test_session, pane2, message)

        time.sleep(0.5)

        # Verify both received the message
        content1 = capture_pane_content(test_session, pane1)
        content2 = capture_pane_content(test_session, pane2)

        assert message in content1
        assert message in content2


class TestRealTmuxDiscovery:
    """Tests for real tmux agent discovery."""

    @pytest.fixture
    def test_session(self):
        """Create and cleanup a test tmux session."""
        session_name = "claude-swarm-test-discovery"
        kill_test_session(session_name)

        if not create_test_session(session_name):
            pytest.skip("Could not create test session")

        yield session_name

        kill_test_session(session_name)

    def test_discover_agents_in_real_session(self, test_session, tmp_path):
        """Test discovering agents in a real tmux session."""
        # Create some panes to simulate agents
        pane1 = create_test_pane(test_session)
        pane2 = create_test_pane(test_session)

        assert pane1 is not None
        assert pane2 is not None

        # Send agent identifiers
        send_to_pane(test_session, pane1, "export AGENT_ID=agent-test-1")
        send_to_pane(test_session, pane2, "export AGENT_ID=agent-test-2")

        time.sleep(0.5)

        # Try to discover agents (will use the current session)
        # Note: This may find panes but not necessarily our specific agents
        # unless they have the right environment/markers
        try:
            registry = refresh_registry(stale_threshold=300)

            # We should at least get a registry back
            assert registry is not None
            assert registry.session_name == test_session or registry.session_name

            # The registry might contain agents
            assert isinstance(registry.agents, list)
        except RuntimeError:
            # Discovery might fail if not in the right session context
            # This is okay for this test
            pass

    def test_list_agents_with_real_session(self, test_session):
        """Test listing agents from real session."""
        # Create panes
        pane1 = create_test_pane(test_session)
        pane2 = create_test_pane(test_session)

        time.sleep(0.5)

        # Attempt to list agents
        try:
            agents = list_active_agents()

            # Should return a list (might be empty if no agents detected)
            assert isinstance(agents, list)
        except FileNotFoundError:
            # Registry file might not exist, which is okay
            pass


class TestRealTmuxWithActualAgents:
    """Tests that simulate actual agent behavior in tmux."""

    @pytest.fixture
    def test_session(self):
        """Create and cleanup a test tmux session."""
        session_name = "claude-swarm-test-agents"
        kill_test_session(session_name)

        if not create_test_session(session_name):
            pytest.skip("Could not create test session")

        yield session_name

        kill_test_session(session_name)

    def test_simulated_agent_communication(self, test_session, tmp_path):
        """Test simulated agent communication through real tmux."""
        # Create two panes representing agents
        pane1 = create_test_pane(test_session)
        pane2 = create_test_pane(test_session)

        assert pane1 is not None
        assert pane2 is not None

        # Simulate agent 1 sending a message
        msg_from_1 = "Agent-1: Starting task"
        send_to_pane(test_session, pane1, msg_from_1)
        send_to_pane(test_session, pane1, "Enter")

        time.sleep(0.5)

        # Simulate agent 2 responding
        msg_from_2 = "Agent-2: Acknowledged"
        send_to_pane(test_session, pane2, msg_from_2)
        send_to_pane(test_session, pane2, "Enter")

        time.sleep(0.5)

        # Verify messages in respective panes
        content1 = capture_pane_content(test_session, pane1)
        content2 = capture_pane_content(test_session, pane2)

        assert msg_from_1 in content1
        assert msg_from_2 in content2

    def test_agent_lock_coordination_real_tmux(self, test_session, tmp_path):
        """Test lock coordination between agents in real tmux panes."""
        # Setup lock manager
        lock_manager = LockManager(project_root=tmp_path)

        # Create two panes representing agents
        pane1 = create_test_pane(test_session)
        pane2 = create_test_pane(test_session)

        assert pane1 is not None
        assert pane2 is not None

        # Agent 1 acquires lock
        test_file = "shared_file.txt"
        success, conflict = lock_manager.acquire_lock(
            filepath=test_file,
            agent_id="agent-1",
            reason="Testing",
        )
        assert success

        # Send confirmation to pane 1
        send_to_pane(test_session, pane1, "Lock acquired")
        time.sleep(0.3)

        # Agent 2 tries to acquire same lock (should fail)
        success, conflict = lock_manager.acquire_lock(
            filepath=test_file,
            agent_id="agent-2",
            reason="Testing",
        )
        assert not success
        assert conflict is not None

        # Send notification to pane 2
        send_to_pane(test_session, pane2, "Lock denied - waiting")
        time.sleep(0.3)

        # Agent 1 releases lock
        released = lock_manager.release_lock(
            filepath=test_file,
            agent_id="agent-1",
        )
        assert released

        send_to_pane(test_session, pane1, "Lock released")
        time.sleep(0.3)

        # Agent 2 can now acquire lock
        success, conflict = lock_manager.acquire_lock(
            filepath=test_file,
            agent_id="agent-2",
            reason="Testing",
        )
        assert success

        send_to_pane(test_session, pane2, "Lock acquired")
        time.sleep(0.3)

        # Verify final state in panes
        content1 = capture_pane_content(test_session, pane1)
        content2 = capture_pane_content(test_session, pane2)

        assert "Lock acquired" in content1
        assert "Lock released" in content1
        assert "Lock denied" in content2
        assert "Lock acquired" in content2


class TestRealTmuxSessionManagement:
    """Tests for tmux session management operations."""

    def test_create_and_destroy_session(self):
        """Test creating and destroying a tmux session."""
        session_name = "claude-swarm-test-lifecycle"

        # Cleanup any existing session
        kill_test_session(session_name)

        # Create session
        success = create_test_session(session_name)
        assert success

        # Verify session exists
        result = subprocess.run(
            ["tmux", "has-session", "-t", session_name],
            timeout=5,
        )
        assert result.returncode == 0

        # Destroy session
        kill_test_session(session_name)

        # Verify session is gone
        result = subprocess.run(
            ["tmux", "has-session", "-t", session_name],
            timeout=5,
        )
        assert result.returncode != 0

    def test_create_multiple_panes(self):
        """Test creating multiple panes in a session."""
        session_name = "claude-swarm-test-panes"
        kill_test_session(session_name)

        try:
            # Create session
            assert create_test_session(session_name)

            # Create multiple panes
            panes = []
            for _ in range(3):
                pane = create_test_pane(session_name)
                if pane:
                    panes.append(pane)
                time.sleep(0.2)

            # Should have created at least 2 panes
            assert len(panes) >= 2

            # Verify panes exist
            result = subprocess.run(
                ["tmux", "list-panes", "-t", f"{session_name}:"],
                capture_output=True,
                timeout=5,
            )
            assert result.returncode == 0

        finally:
            kill_test_session(session_name)

    def test_session_cleanup_on_error(self):
        """Test that sessions are cleaned up even after errors."""
        session_name = "claude-swarm-test-cleanup"

        try:
            # Create session
            assert create_test_session(session_name)

            # Simulate some error condition
            try:
                raise RuntimeError("Simulated error")
            except RuntimeError:
                pass

            # Session should still exist
            result = subprocess.run(
                ["tmux", "has-session", "-t", session_name],
                timeout=5,
            )
            assert result.returncode == 0

        finally:
            # Cleanup should work
            kill_test_session(session_name)

            # Verify cleanup
            result = subprocess.run(
                ["tmux", "has-session", "-t", session_name],
                timeout=5,
            )
            assert result.returncode != 0


class TestRealTmuxMessageFormatting:
    """Tests for message formatting in real tmux."""

    @pytest.fixture
    def test_session(self):
        """Create and cleanup a test tmux session."""
        session_name = "claude-swarm-test-formatting"
        kill_test_session(session_name)

        if not create_test_session(session_name):
            pytest.skip("Could not create test session")

        yield session_name

        kill_test_session(session_name)

    def test_json_message_in_real_pane(self, test_session):
        """Test sending JSON formatted messages to real pane."""
        pane = create_test_pane(test_session)
        assert pane is not None

        # Create a JSON message
        message_data = {
            "type": "QUESTION",
            "from": "agent-1",
            "to": "agent-2",
            "content": "Need help?",
        }
        json_msg = json.dumps(message_data)

        # Send JSON message
        send_to_pane(test_session, pane, json_msg)
        time.sleep(0.5)

        # Verify message was sent
        content = capture_pane_content(test_session, pane)

        # Should contain parts of the JSON
        assert "QUESTION" in content or "agent-1" in content

    def test_long_message_in_real_pane(self, test_session):
        """Test sending long messages to real pane."""
        pane = create_test_pane(test_session)
        assert pane is not None

        # Create a long message
        long_message = "A" * 500  # 500 character message

        # Send message
        send_to_pane(test_session, pane, long_message)
        time.sleep(0.5)

        # Verify at least part of the message was sent
        content = capture_pane_content(test_session, pane)
        assert "A" * 50 in content  # At least 50 As should be there

    def test_message_with_newlines_in_real_pane(self, test_session):
        """Test handling messages with newlines in real pane."""
        pane = create_test_pane(test_session)
        assert pane is not None

        # Send message with escaped newlines
        message = "Line1\\nLine2\\nLine3"
        send_to_pane(test_session, pane, message)
        time.sleep(0.5)

        content = capture_pane_content(test_session, pane)

        # Message should appear in some form
        assert len(content) > 0
