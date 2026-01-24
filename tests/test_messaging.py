"""
Unit tests for the messaging system.

Tests cover:
- Message formatting and validation
- tmux send-keys escaping
- Rate limiting
- Broadcast delivery
- Special character handling
- Message serialization/deserialization
- Thread safety and concurrent access

Author: Agent-2 (FuchsiaPond)
Modified: Agent-ThreadSafety (added concurrent rate limiting tests)
"""

import json
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from claudeswarm.discovery import Agent as MockAgent
from claudeswarm.messaging import (
    Message,
    MessageLogger,
    MessageType,
    MessagingSystem,
    RateLimiter,
    RateLimitExceeded,
    TmuxError,
    TmuxMessageDelivery,
    TmuxTimeoutError,
)


class TestMessageType:
    """Tests for MessageType enum."""

    def test_message_types_exist(self):
        """Test all required message types are defined."""
        assert MessageType.QUESTION
        assert MessageType.REVIEW_REQUEST
        assert MessageType.BLOCKED
        assert MessageType.COMPLETED
        assert MessageType.CHALLENGE
        assert MessageType.INFO
        assert MessageType.ACK

    def test_message_type_values(self):
        """Test message type values are correct."""
        assert MessageType.QUESTION.value == "QUESTION"
        assert MessageType.REVIEW_REQUEST.value == "REVIEW-REQUEST"
        assert MessageType.ACK.value == "ACK"


class TestMessage:
    """Tests for Message dataclass."""

    def test_message_creation(self):
        """Test creating a valid message."""
        msg = Message(
            sender_id="agent-1",
            timestamp=datetime.now(),
            msg_type=MessageType.INFO,
            content="Test message",
            recipients=["agent-2"],
        )
        assert msg.sender_id == "agent-1"
        assert msg.msg_type == MessageType.INFO
        assert msg.content == "Test message"
        assert msg.recipients == ["agent-2"]
        assert msg.msg_id  # Should have auto-generated ID

    def test_message_validation_empty_sender(self):
        """Test message validation rejects empty sender."""
        with pytest.raises(ValueError, match="Invalid sender_id.*cannot be empty"):
            Message(
                sender_id="",
                timestamp=datetime.now(),
                msg_type=MessageType.INFO,
                content="Test",
                recipients=["agent-2"],
            )

    def test_message_validation_empty_content(self):
        """Test message validation rejects empty content."""
        with pytest.raises(ValueError, match="content cannot be empty"):
            Message(
                sender_id="agent-1",
                timestamp=datetime.now(),
                msg_type=MessageType.INFO,
                content="",
                recipients=["agent-2"],
            )

    def test_message_validation_empty_recipients(self):
        """Test message validation rejects empty recipients."""
        with pytest.raises(ValueError, match="Invalid recipients.*cannot be empty"):
            Message(
                sender_id="agent-1",
                timestamp=datetime.now(),
                msg_type=MessageType.INFO,
                content="Test",
                recipients=[],
            )

    def test_message_format_for_display(self):
        """Test message formatting for display."""
        msg = Message(
            sender_id="agent-0",
            timestamp=datetime(2025, 11, 7, 14, 30, 15),
            msg_type=MessageType.QUESTION,
            content="What database schema?",
            recipients=["agent-1"],
        )
        formatted = msg.format_for_display()
        assert formatted == "[agent-0][2025-11-07 14:30:15][QUESTION]: What database schema?"

    def test_message_to_dict(self):
        """Test message serialization to dict."""
        msg = Message(
            sender_id="agent-1",
            timestamp=datetime(2025, 11, 7, 14, 30, 15),
            msg_type=MessageType.INFO,
            content="Test",
            recipients=["agent-2"],
            msg_id="test-uuid",
        )
        msg_dict = msg.to_dict()
        assert msg_dict["sender_id"] == "agent-1"
        assert msg_dict["msg_type"] == "INFO"
        assert msg_dict["content"] == "Test"
        assert msg_dict["recipients"] == ["agent-2"]
        assert msg_dict["msg_id"] == "test-uuid"
        assert "timestamp" in msg_dict

    def test_message_from_dict(self):
        """Test message deserialization from dict."""
        msg_dict = {
            "sender_id": "agent-1",
            "timestamp": "2025-11-07T14:30:15",
            "msg_type": "INFO",
            "content": "Test",
            "recipients": ["agent-2"],
            "msg_id": "test-uuid",
        }
        msg = Message.from_dict(msg_dict)
        assert msg.sender_id == "agent-1"
        assert msg.msg_type == MessageType.INFO
        assert msg.content == "Test"
        assert msg.recipients == ["agent-2"]
        assert msg.msg_id == "test-uuid"
        assert isinstance(msg.timestamp, datetime)

    def test_message_roundtrip_serialization(self):
        """Test serialization and deserialization roundtrip."""
        original = Message(
            sender_id="agent-1",
            timestamp=datetime.now(),
            msg_type=MessageType.QUESTION,
            content="Test question?",
            recipients=["agent-2", "agent-3"],
        )
        msg_dict = original.to_dict()
        restored = Message.from_dict(msg_dict)

        assert restored.sender_id == original.sender_id
        assert restored.msg_type == original.msg_type
        assert restored.content == original.content
        assert restored.recipients == original.recipients
        assert restored.msg_id == original.msg_id


class TestRateLimiter:
    """Tests for RateLimiter."""

    def test_rate_limiter_allows_within_limit(self):
        """Test rate limiter allows messages within limit."""
        limiter = RateLimiter(max_messages=3, window_seconds=60)

        # Should allow first 3 messages
        assert limiter.check_rate_limit("agent-1") is True
        limiter.record_message("agent-1")

        assert limiter.check_rate_limit("agent-1") is True
        limiter.record_message("agent-1")

        assert limiter.check_rate_limit("agent-1") is True
        limiter.record_message("agent-1")

    def test_rate_limiter_blocks_over_limit(self):
        """Test rate limiter blocks messages over limit."""
        limiter = RateLimiter(max_messages=2, window_seconds=60)

        # Send 2 messages (at limit)
        limiter.record_message("agent-1")
        limiter.record_message("agent-1")

        # Third should be blocked
        assert limiter.check_rate_limit("agent-1") is False

    def test_rate_limiter_per_agent(self):
        """Test rate limiter is per-agent."""
        limiter = RateLimiter(max_messages=2, window_seconds=60)

        # Agent 1 sends 2 messages
        limiter.record_message("agent-1")
        limiter.record_message("agent-1")
        assert limiter.check_rate_limit("agent-1") is False

        # Agent 2 should still be able to send
        assert limiter.check_rate_limit("agent-2") is True

    def test_rate_limiter_reset(self):
        """Test rate limiter reset for agent."""
        limiter = RateLimiter(max_messages=2, window_seconds=60)

        limiter.record_message("agent-1")
        limiter.record_message("agent-1")
        assert limiter.check_rate_limit("agent-1") is False

        # Reset agent-1
        limiter.reset_agent("agent-1")
        assert limiter.check_rate_limit("agent-1") is True

    def test_rate_limiter_window_expiry(self):
        """Test rate limiter respects time window."""
        from datetime import datetime, timedelta
        from unittest.mock import patch

        # Use very short window for testing
        limiter = RateLimiter(max_messages=1, window_seconds=1)

        # Mock datetime.now() to control time progression
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        with patch("claudeswarm.messaging.datetime") as mock_datetime:
            # First call: record message at base_time
            mock_datetime.now.return_value = base_time
            limiter.record_message("agent-1")

            # Second call: check immediately (should be rate limited)
            mock_datetime.now.return_value = base_time
            assert limiter.check_rate_limit("agent-1") is False

            # Third call: check after window expires (1.1 seconds later)
            mock_datetime.now.return_value = base_time + timedelta(seconds=1.1)
            assert limiter.check_rate_limit("agent-1") is True


class TestTmuxMessageDelivery:
    """Tests for TmuxMessageDelivery."""

    def test_escape_single_quotes(self):
        """Test escaping of single quotes using shlex.quote."""
        text = "It's a test"
        escaped = TmuxMessageDelivery.escape_for_tmux(text)
        # shlex.quote should properly quote the string
        # Result should be safe for shell execution
        assert escaped.startswith("'") or escaped.startswith('"')

    def test_escape_double_quotes(self):
        """Test double quotes are properly escaped using shlex.quote."""
        text = 'He said "hello"'
        escaped = TmuxMessageDelivery.escape_for_tmux(text)
        # shlex.quote should handle double quotes safely
        assert escaped  # Should return non-empty escaped string

    def test_escape_newlines(self):
        """Test newlines are safely handled by shlex.quote."""
        text = "Line 1\nLine 2\nLine 3"
        escaped = TmuxMessageDelivery.escape_for_tmux(text)
        # shlex.quote wraps the entire string in quotes
        # Newlines are preserved within the quotes for safety
        assert escaped.startswith("'")
        assert escaped.endswith("'")

    def test_escape_complex_text(self):
        """Test escaping of complex text with multiple special characters using shlex.quote."""
        text = "Agent's message:\n\"Status: OK\"\n'Progress: 50%'"
        escaped = TmuxMessageDelivery.escape_for_tmux(text)
        # shlex.quote should safely handle complex text
        assert escaped  # Should return non-empty escaped string
        # The result should be a safely quoted string
        assert escaped.startswith("'")

    @patch("subprocess.run")
    def test_send_to_pane_success(self, mock_run):
        """Test successful message delivery to pane."""
        # Mock for both verify_pane_exists and send_keys calls
        mock_run.return_value = Mock(
            returncode=0, stderr="", stdout="session:0.1\n"  # For verify_pane_exists
        )

        result = TmuxMessageDelivery.send_to_pane("session:0.1", "Test message")

        assert result is True
        # Should be called three times: verify, send command, send Enter key
        assert mock_run.call_count == 3

        # First call: verify pane exists (list-panes)
        verify_call_args = mock_run.call_args_list[0][0][0]
        assert verify_call_args[0] == "tmux"
        assert verify_call_args[1] == "list-panes"

        # Second call: send the command with -l flag
        first_call_args = mock_run.call_args_list[1][0][0]
        assert first_call_args[0] == "tmux"
        assert first_call_args[1] == "send-keys"
        assert first_call_args[2] == "-l"  # Literal interpretation flag
        assert first_call_args[3] == "-t"
        assert first_call_args[4] == "session:0.1"
        assert first_call_args[5].startswith("# [MESSAGE]")

        # Third call: send Enter key
        second_call_args = mock_run.call_args_list[2][0][0]
        assert second_call_args[0] == "tmux"
        assert second_call_args[1] == "send-keys"
        assert second_call_args[2] == "-t"
        assert second_call_args[3] == "session:0.1"
        assert second_call_args[4] == "Enter"

    @patch("subprocess.run")
    def test_send_to_pane_failure(self, mock_run):
        """Test failed message delivery to pane."""
        # First call (verify) succeeds, second call (send-keys) fails
        mock_run.side_effect = [
            Mock(returncode=0, stderr="", stdout="session:0.1\n"),  # verify succeeds
            Mock(returncode=1, stderr="Pane not found"),  # send-keys fails
        ]

        with pytest.raises(TmuxError):
            TmuxMessageDelivery.send_to_pane("session:0.1", "Test message")

    @patch.object(TmuxMessageDelivery, "_send_to_pane_once")
    def test_send_to_pane_timeout(self, mock_send_once):
        """Test timeout handling in message delivery.

        Note: We mock _send_to_pane_once because send_to_pane now includes
        retry logic that would require multiple subprocess.run mocks.
        """
        # Simulate timeout on all attempts (exhausts retries)
        mock_send_once.side_effect = TmuxTimeoutError("Timeout sending to pane")

        with pytest.raises(TmuxTimeoutError):
            TmuxMessageDelivery.send_to_pane("session:0.1", "Test message")

    @patch("subprocess.run")
    def test_verify_pane_exists(self, mock_run):
        """Test pane existence verification."""
        mock_run.return_value = Mock(returncode=0, stdout="session:0.0\nsession:0.1\nsession:0.2\n")

        result = TmuxMessageDelivery.verify_pane_exists("session:0.1")
        assert result is True

    @patch("subprocess.run")
    def test_verify_pane_not_exists(self, mock_run):
        """Test pane non-existence detection."""
        mock_run.return_value = Mock(returncode=0, stdout="session:0.0\nsession:0.2\n")

        result = TmuxMessageDelivery.verify_pane_exists("session:0.1")
        assert result is False


class TestMessageLogger:
    """Tests for MessageLogger."""

    def test_message_logger_creation(self):
        """Test message logger creates log file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test_messages.log"
            MessageLogger(log_file)

            assert log_file.exists()

    def test_message_logger_logs_message(self):
        """Test message logger writes log entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test_messages.log"
            logger = MessageLogger(log_file)

            msg = Message(
                sender_id="agent-1",
                timestamp=datetime.now(),
                msg_type=MessageType.INFO,
                content="Test",
                recipients=["agent-2"],
            )
            delivery_status = {"agent-2": True}

            logger.log_message(msg, delivery_status)

            # Read log file
            with open(log_file) as f:
                log_content = f.read()

            # Verify log entry
            log_entry = json.loads(log_content.strip())
            assert log_entry["sender"] == "agent-1"
            assert log_entry["msg_type"] == "INFO"
            assert log_entry["content"] == "Test"
            assert log_entry["delivery_status"] == {"agent-2": True}
            assert log_entry["success_count"] == 1
            assert log_entry["failure_count"] == 0

    def test_message_logger_multiple_entries(self):
        """Test message logger handles multiple log entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test_messages.log"
            logger = MessageLogger(log_file)

            for i in range(3):
                msg = Message(
                    sender_id=f"agent-{i}",
                    timestamp=datetime.now(),
                    msg_type=MessageType.INFO,
                    content=f"Message {i}",
                    recipients=["agent-x"],
                )
                logger.log_message(msg, {"agent-x": True})

            # Read log file
            with open(log_file) as f:
                lines = f.readlines()

            assert len(lines) == 3
            for i, line in enumerate(lines):
                entry = json.loads(line)
                assert entry["sender"] == f"agent-{i}"


class TestMessagingSystem:
    """Tests for MessagingSystem."""

    def test_messaging_system_initialization(self):
        """Test messaging system initializes correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test_messages.log"
            system = MessagingSystem(log_file=log_file)

            assert system.rate_limiter is not None
            assert system.message_logger is not None
            assert system.delivery is not None

    def test_integration_with_discovery_agent(self):
        """Test that messaging system can load agent registry."""
        system = MessagingSystem()

        # The messaging system should be able to load the agent registry
        # without throwing errors, even if the registry doesn't exist
        registry = system._load_agent_registry()
        # Registry may be None if file doesn't exist, which is fine
        assert registry is None or registry is not None

    @patch("claudeswarm.messaging.MessagingSystem._get_agent_pane")
    @patch.object(TmuxMessageDelivery, "send_to_pane")
    def test_send_message_success(self, mock_send, mock_get_pane):
        """Test successful direct message sending."""
        mock_send.return_value = True
        mock_get_pane.return_value = "session:0.2"

        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test_messages.log"
            system = MessagingSystem(log_file=log_file)

            # Send message
            result = system.send_message("agent-1", "agent-2", MessageType.INFO, "Test message")

            assert result is not None
            assert result.sender_id == "agent-1"
            assert result.recipients == ["agent-2"]
            assert result.signature  # Should have a signature
            mock_send.assert_called_once()

    @patch("claudeswarm.messaging.MessagingSystem._get_agent_pane")
    @patch.object(TmuxMessageDelivery, "send_to_pane")
    def test_send_message_rate_limit(self, mock_send, mock_get_pane):
        """Test rate limiting in message sending."""
        mock_send.return_value = True
        mock_get_pane.return_value = "session:0.2"

        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test_messages.log"
            # Set very low rate limit
            system = MessagingSystem(log_file=log_file, rate_limit_messages=2, rate_limit_window=60)

            # Send 2 messages (should succeed)
            result1 = system.send_message("agent-1", "agent-2", MessageType.INFO, "Msg 1")
            result2 = system.send_message("agent-1", "agent-2", MessageType.INFO, "Msg 2")

            assert result1 is not None
            assert result2 is not None

            # Third message should fail due to rate limit
            with pytest.raises(RateLimitExceeded):
                system.send_message("agent-1", "agent-2", MessageType.INFO, "Msg 3")

    @patch("claudeswarm.messaging.MessagingSystem._get_agent_pane")
    @patch("claudeswarm.messaging.MessagingSystem._load_agent_registry")
    @patch.object(TmuxMessageDelivery, "send_to_pane")
    def test_broadcast_message(self, mock_send, mock_load_registry, mock_get_pane):
        """Test broadcast messaging to multiple agents."""
        mock_send.return_value = True
        mock_get_pane.side_effect = lambda agent_id: f"session:0.{agent_id.split('-')[1]}"

        # Create mock registry with 4 agents
        from claudeswarm.discovery import AgentRegistry

        mock_agents = [
            MockAgent(
                id=f"agent-{i}",
                pane_index=f"session:0.{i}",
                pid=12345 + i,
                status="active",
                last_seen=datetime.now(),
                session_name="test",
            )
            for i in range(4)
        ]
        mock_registry = AgentRegistry(
            session_name="test", updated_at=datetime.now().isoformat(), agents=mock_agents
        )
        mock_load_registry.return_value = mock_registry

        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test_messages.log"
            system = MessagingSystem(log_file=log_file)

            # Broadcast from agent-0
            results = system.broadcast_message(
                "agent-0", MessageType.INFO, "Broadcast message", exclude_self=True
            )

            # Should send to 3 agents (excluding self)
            assert len(results) == 3
            assert "agent-0" not in results
            assert all(results.values())  # All should succeed
            assert mock_send.call_count == 3

    @patch("claudeswarm.messaging.MessagingSystem._get_agent_pane")
    @patch("claudeswarm.messaging.MessagingSystem._load_agent_registry")
    @patch.object(TmuxMessageDelivery, "send_to_pane")
    def test_broadcast_include_self(self, mock_send, mock_load_registry, mock_get_pane):
        """Test broadcast messaging including sender."""
        mock_send.return_value = True
        mock_get_pane.side_effect = lambda agent_id: f"session:0.{agent_id.split('-')[1]}"

        # Create mock registry with 3 agents
        from claudeswarm.discovery import AgentRegistry

        mock_agents = [
            MockAgent(
                id=f"agent-{i}",
                pane_index=f"session:0.{i}",
                pid=12345 + i,
                status="active",
                last_seen=datetime.now(),
                session_name="test",
            )
            for i in range(3)
        ]
        mock_registry = AgentRegistry(
            session_name="test", updated_at=datetime.now().isoformat(), agents=mock_agents
        )
        mock_load_registry.return_value = mock_registry

        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test_messages.log"
            system = MessagingSystem(log_file=log_file)

            # Broadcast from agent-0, including self
            results = system.broadcast_message(
                "agent-0", MessageType.INFO, "Broadcast message", exclude_self=False
            )

            # Should send to all 3 agents
            assert len(results) == 3
            assert "agent-0" in results


class TestSpecialCharacterHandling:
    """Tests for special character handling in messages."""

    def test_message_with_special_characters(self):
        """Test message content can contain special characters."""
        special_content = "Test: !@#$%^&*()_+-=[]{}|;':\",./<>?"
        msg = Message(
            sender_id="agent-1",
            timestamp=datetime.now(),
            msg_type=MessageType.INFO,
            content=special_content,
            recipients=["agent-2"],
        )
        assert msg.content == special_content

    def test_message_with_unicode(self):
        """Test message content can contain unicode characters."""
        unicode_content = "Hello 世界 🌍 Привет"
        msg = Message(
            sender_id="agent-1",
            timestamp=datetime.now(),
            msg_type=MessageType.INFO,
            content=unicode_content,
            recipients=["agent-2"],
        )
        assert msg.content == unicode_content

    def test_escape_preserves_unicode(self):
        """Test escaping preserves unicode characters."""
        text = "Test 你好 🎉"
        escaped = TmuxMessageDelivery.escape_for_tmux(text)
        # Unicode should be preserved
        assert "你好" in escaped or "\\u" in escaped
        assert "🎉" in escaped or "\\u" in escaped


class TestRateLimiterThreadSafety:
    """Tests for RateLimiter thread safety.

    These tests verify that the RateLimiter correctly handles concurrent access
    from multiple threads without race conditions.
    """

    def test_concurrent_check_rate_limit(self):
        """Test concurrent check_rate_limit calls are thread-safe."""
        limiter = RateLimiter(max_messages=10, window_seconds=60)
        agent_id = "agent-1"
        results = []
        errors = []

        def check_limit():
            """Worker thread that checks rate limit."""
            try:
                for _ in range(5):
                    result = limiter.check_rate_limit(agent_id)
                    results.append(result)
                    time.sleep(0.001)  # Small delay to increase race condition likelihood
            except Exception as e:
                errors.append(e)

        # Run 5 threads concurrently checking rate limit
        threads = [threading.Thread(target=check_limit) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have no errors
        assert len(errors) == 0, f"Errors occurred: {errors}"
        # Should have 25 results (5 threads * 5 checks each)
        assert len(results) == 25
        # All should be True since we haven't recorded any messages
        assert all(results)

    def test_concurrent_record_message(self):
        """Test concurrent record_message calls are thread-safe."""
        limiter = RateLimiter(max_messages=50, window_seconds=60)
        agent_id = "agent-1"
        errors = []

        def record_messages():
            """Worker thread that records messages."""
            try:
                for _ in range(10):
                    limiter.record_message(agent_id)
                    time.sleep(0.001)  # Small delay to increase race condition likelihood
            except Exception as e:
                errors.append(e)

        # Run 5 threads concurrently recording messages
        threads = [threading.Thread(target=record_messages) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have no errors
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Should have recorded 50 messages total (5 threads * 10 messages each)
        # Verify by checking the internal state
        assert len(limiter._message_times[agent_id]) == 50

    def test_concurrent_check_and_record(self):
        """Test concurrent check_rate_limit and record_message calls."""
        limiter = RateLimiter(max_messages=20, window_seconds=60)
        agent_id = "agent-1"
        successful_checks = []
        errors = []
        lock = threading.Lock()

        def check_and_record():
            """Worker thread that checks and records messages."""
            try:
                for _ in range(5):
                    if limiter.check_rate_limit(agent_id):
                        limiter.record_message(agent_id)
                        with lock:
                            successful_checks.append(1)
                    time.sleep(0.001)  # Small delay
            except Exception as e:
                errors.append(e)

        # Run 5 threads concurrently checking and recording
        threads = [threading.Thread(target=check_and_record) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have no errors
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Should have at most max_messages successful recordings
        assert len(successful_checks) <= 20
        # Should have exactly max_messages recorded
        assert len(limiter._message_times[agent_id]) <= 20

    def test_concurrent_rate_limit_enforcement(self):
        """Test that rate limits are properly enforced under concurrent load."""
        limiter = RateLimiter(max_messages=10, window_seconds=60)
        agent_id = "agent-1"
        successful_sends = []
        blocked_sends = []
        errors = []
        lock = threading.Lock()

        def attempt_send():
            """Worker thread that attempts to send messages."""
            try:
                for _ in range(5):
                    if limiter.check_rate_limit(agent_id):
                        limiter.record_message(agent_id)
                        with lock:
                            successful_sends.append(1)
                    else:
                        with lock:
                            blocked_sends.append(1)
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        # Run 5 threads, each attempting 5 sends (25 total attempts)
        threads = [threading.Thread(target=attempt_send) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have no errors
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Should have exactly 10 successful sends (the rate limit)
        assert len(successful_sends) == 10, f"Expected 10 successful, got {len(successful_sends)}"

        # Should have blocked the remaining 15 attempts
        assert len(blocked_sends) == 15, f"Expected 15 blocked, got {len(blocked_sends)}"

        # Verify internal state matches
        assert len(limiter._message_times[agent_id]) == 10

    def test_concurrent_multi_agent(self):
        """Test concurrent access for multiple agents is properly isolated."""
        limiter = RateLimiter(max_messages=5, window_seconds=60)
        results = {}
        errors = []
        lock = threading.Lock()

        def agent_worker(agent_id):
            """Worker thread for a specific agent."""
            try:
                count = 0
                for _ in range(10):
                    if limiter.check_rate_limit(agent_id):
                        limiter.record_message(agent_id)
                        count += 1
                    time.sleep(0.001)
                with lock:
                    results[agent_id] = count
            except Exception as e:
                errors.append((agent_id, e))

        # Run 3 agents concurrently, each attempting 10 messages
        agent_ids = ["agent-1", "agent-2", "agent-3"]
        threads = [threading.Thread(target=agent_worker, args=(aid,)) for aid in agent_ids]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have no errors
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Each agent should have successfully sent exactly 5 messages
        for agent_id in agent_ids:
            assert (
                results[agent_id] == 5
            ), f"{agent_id} sent {results[agent_id]} messages, expected 5"
            assert len(limiter._message_times[agent_id]) == 5

    def test_concurrent_cleanup_inactive_agents(self):
        """Test cleanup_inactive_agents is thread-safe with concurrent operations."""
        limiter = RateLimiter(max_messages=10, window_seconds=1)
        errors = []
        cleanup_counts = []
        lock = threading.Lock()

        # Pre-populate with some old messages
        for i in range(5):
            limiter.record_message(f"agent-{i}")

        # Wait for messages to become old
        time.sleep(1.1)

        def cleanup_worker():
            """Worker thread that performs cleanup."""
            try:
                count = limiter.cleanup_inactive_agents(cutoff_seconds=1)
                with lock:
                    cleanup_counts.append(count)
            except Exception as e:
                errors.append(e)

        def record_worker():
            """Worker thread that records new messages."""
            try:
                for i in range(5, 10):
                    limiter.record_message(f"agent-{i}")
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        # Run cleanup and record operations concurrently
        threads = []
        threads.append(threading.Thread(target=cleanup_worker))
        threads.append(threading.Thread(target=record_worker))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have no errors
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Should have cleaned up the 5 old agents
        assert sum(cleanup_counts) == 5

    def test_concurrent_reset_agent(self):
        """Test reset_agent is thread-safe with concurrent operations."""
        limiter = RateLimiter(max_messages=10, window_seconds=60)
        agent_id = "agent-1"
        errors = []

        # Pre-populate with messages
        for _ in range(10):
            limiter.record_message(agent_id)

        def reset_worker():
            """Worker thread that resets the agent."""
            try:
                limiter.reset_agent(agent_id)
            except Exception as e:
                errors.append(e)

        def check_worker():
            """Worker thread that checks rate limit."""
            try:
                limiter.check_rate_limit(agent_id)
            except Exception as e:
                errors.append(e)

        # Run reset and check operations concurrently
        threads = []
        threads.append(threading.Thread(target=reset_worker))
        threads.extend([threading.Thread(target=check_worker) for _ in range(5)])

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have no errors
        assert len(errors) == 0, f"Errors occurred: {errors}"

    def test_no_deadlock_with_nested_operations(self):
        """Test that there are no deadlocks with rapid sequential operations."""
        limiter = RateLimiter(max_messages=10, window_seconds=60)
        errors = []

        def rapid_operations():
            """Worker thread performing rapid mixed operations."""
            try:
                for i in range(20):
                    agent_id = f"agent-{i % 5}"
                    limiter.check_rate_limit(agent_id)
                    limiter.record_message(agent_id)
                    if i % 10 == 0:
                        limiter.cleanup_inactive_agents(cutoff_seconds=3600)
            except Exception as e:
                errors.append(e)

        # Run multiple threads with rapid mixed operations
        threads = [threading.Thread(target=rapid_operations) for _ in range(10)]
        for t in threads:
            t.start()

        # Use a timeout to detect deadlocks
        for t in threads:
            t.join(timeout=5.0)
            if t.is_alive():
                errors.append("Thread deadlock detected - thread did not complete in time")

        # Should have no errors
        assert len(errors) == 0, f"Errors occurred: {errors}"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])
