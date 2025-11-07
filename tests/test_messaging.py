"""
Unit tests for the messaging system.

Tests cover:
- Message formatting and validation
- tmux send-keys escaping
- Rate limiting
- Broadcast delivery
- Special character handling
- Message serialization/deserialization

Author: Agent-2 (FuchsiaPond)
"""

import json
import pytest
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, call
from claudeswarm.messaging import (
    MessageType,
    Message,
    RateLimiter,
    TmuxMessageDelivery,
    MessageLogger,
    MessagingSystem
)
from claudeswarm.discovery import Agent as MockAgent


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
            recipients=["agent-2"]
        )
        assert msg.sender_id == "agent-1"
        assert msg.msg_type == MessageType.INFO
        assert msg.content == "Test message"
        assert msg.recipients == ["agent-2"]
        assert msg.msg_id  # Should have auto-generated ID

    def test_message_validation_empty_sender(self):
        """Test message validation rejects empty sender."""
        with pytest.raises(ValueError, match="sender_id cannot be empty"):
            Message(
                sender_id="",
                timestamp=datetime.now(),
                msg_type=MessageType.INFO,
                content="Test",
                recipients=["agent-2"]
            )

    def test_message_validation_empty_content(self):
        """Test message validation rejects empty content."""
        with pytest.raises(ValueError, match="content cannot be empty"):
            Message(
                sender_id="agent-1",
                timestamp=datetime.now(),
                msg_type=MessageType.INFO,
                content="",
                recipients=["agent-2"]
            )

    def test_message_validation_empty_recipients(self):
        """Test message validation rejects empty recipients."""
        with pytest.raises(ValueError, match="recipients cannot be empty"):
            Message(
                sender_id="agent-1",
                timestamp=datetime.now(),
                msg_type=MessageType.INFO,
                content="Test",
                recipients=[]
            )

    def test_message_format_for_display(self):
        """Test message formatting for display."""
        msg = Message(
            sender_id="agent-0",
            timestamp=datetime(2025, 11, 7, 14, 30, 15),
            msg_type=MessageType.QUESTION,
            content="What database schema?",
            recipients=["agent-1"]
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
            msg_id="test-uuid"
        )
        msg_dict = msg.to_dict()
        assert msg_dict['sender_id'] == "agent-1"
        assert msg_dict['msg_type'] == "INFO"
        assert msg_dict['content'] == "Test"
        assert msg_dict['recipients'] == ["agent-2"]
        assert msg_dict['msg_id'] == "test-uuid"
        assert 'timestamp' in msg_dict

    def test_message_from_dict(self):
        """Test message deserialization from dict."""
        msg_dict = {
            'sender_id': 'agent-1',
            'timestamp': '2025-11-07T14:30:15',
            'msg_type': 'INFO',
            'content': 'Test',
            'recipients': ['agent-2'],
            'msg_id': 'test-uuid'
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
            recipients=["agent-2", "agent-3"]
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
        # Use very short window for testing
        limiter = RateLimiter(max_messages=1, window_seconds=1)

        limiter.record_message("agent-1")
        assert limiter.check_rate_limit("agent-1") is False

        # Wait for window to expire
        time.sleep(1.1)
        assert limiter.check_rate_limit("agent-1") is True


class TestTmuxMessageDelivery:
    """Tests for TmuxMessageDelivery."""

    def test_escape_single_quotes(self):
        """Test escaping of single quotes."""
        text = "It's a test"
        escaped = TmuxMessageDelivery.escape_for_tmux(text)
        # Single quotes should be escaped as '"'"'
        assert "'" not in escaped or "'\"'\"'" in escaped

    def test_escape_double_quotes(self):
        """Test double quotes are preserved."""
        text = 'He said "hello"'
        escaped = TmuxMessageDelivery.escape_for_tmux(text)
        assert '"' in escaped  # Double quotes should be in escaped string

    def test_escape_newlines(self):
        """Test newlines are escaped."""
        text = "Line 1\nLine 2\nLine 3"
        escaped = TmuxMessageDelivery.escape_for_tmux(text)
        assert "\n" not in escaped  # No literal newlines
        assert "\\n" in escaped  # Should have escaped newlines

    def test_escape_complex_text(self):
        """Test escaping of complex text with multiple special characters."""
        text = "Agent's message:\n\"Status: OK\"\n'Progress: 50%'"
        escaped = TmuxMessageDelivery.escape_for_tmux(text)
        # Should not contain literal newlines
        assert "\n" not in escaped
        assert "\\n" in escaped

    @patch('subprocess.run')
    def test_send_to_pane_success(self, mock_run):
        """Test successful message delivery to pane."""
        mock_run.return_value = Mock(returncode=0, stderr="")

        result = TmuxMessageDelivery.send_to_pane("session:0.1", "Test message")

        assert result is True
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == 'tmux'
        assert args[1] == 'send-keys'
        assert args[2] == '-t'
        assert args[3] == 'session:0.1'

    @patch('subprocess.run')
    def test_send_to_pane_failure(self, mock_run):
        """Test failed message delivery to pane."""
        mock_run.return_value = Mock(returncode=1, stderr="Pane not found")

        result = TmuxMessageDelivery.send_to_pane("session:0.1", "Test message")

        assert result is False

    @patch('subprocess.run')
    def test_send_to_pane_timeout(self, mock_run):
        """Test timeout handling in message delivery."""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired('tmux', 5)

        result = TmuxMessageDelivery.send_to_pane("session:0.1", "Test message")

        assert result is False

    @patch('subprocess.run')
    def test_verify_pane_exists(self, mock_run):
        """Test pane existence verification."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="session:0.0\nsession:0.1\nsession:0.2\n"
        )

        result = TmuxMessageDelivery.verify_pane_exists("session:0.1")
        assert result is True

    @patch('subprocess.run')
    def test_verify_pane_not_exists(self, mock_run):
        """Test pane non-existence detection."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="session:0.0\nsession:0.2\n"
        )

        result = TmuxMessageDelivery.verify_pane_exists("session:0.1")
        assert result is False


class TestMessageLogger:
    """Tests for MessageLogger."""

    def test_message_logger_creation(self):
        """Test message logger creates log file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test_messages.log"
            logger = MessageLogger(log_file)

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
                recipients=["agent-2"]
            )
            delivery_status = {"agent-2": True}

            logger.log_message(msg, delivery_status)

            # Read log file
            with open(log_file) as f:
                log_content = f.read()

            # Verify log entry
            log_entry = json.loads(log_content.strip())
            assert log_entry['sender'] == "agent-1"
            assert log_entry['msg_type'] == "INFO"
            assert log_entry['content'] == "Test"
            assert log_entry['delivery_status'] == {"agent-2": True}
            assert log_entry['success_count'] == 1
            assert log_entry['failure_count'] == 0

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
                    recipients=["agent-x"]
                )
                logger.log_message(msg, {"agent-x": True})

            # Read log file
            with open(log_file) as f:
                lines = f.readlines()

            assert len(lines) == 3
            for i, line in enumerate(lines):
                entry = json.loads(line)
                assert entry['sender'] == f"agent-{i}"


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
        """Test registering mock agents."""
        system = MessagingSystem()

        agent = MockAgent(
            id="agent-1",
            pane_index="session:0.1",
            pid=12345,
            status="active",
            last_seen=datetime.now(),
            session_name="test-session"
        )

        
        assert "agent-1" in system._agent_registry

    @patch.object(TmuxMessageDelivery, 'send_to_pane')
    def test_send_message_success(self, mock_send):
        """Test successful direct message sending."""
        mock_send.return_value = True

        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test_messages.log"
            system = MessagingSystem(log_file=log_file)

            # Register mock agents
            agent1 = MockAgent(
                id="agent-1",
                pane_index="session:0.1",
                pid=12345,
                status="active",
                last_seen=datetime.now(),
                session_name="test"
            )
            agent2 = MockAgent(
                id="agent-2",
                pane_index="session:0.2",
                pid=12346,
                status="active",
                last_seen=datetime.now(),
                session_name="test"
            )
            system.register_mock_agent(agent1)
            system.register_mock_agent(agent2)

            # Send message
            result = system.send_message(
                "agent-1",
                "agent-2",
                MessageType.INFO,
                "Test message"
            )

            assert result is not None
            assert result.sender_id == "agent-1"
            assert result.recipients == ["agent-2"]
            mock_send.assert_called_once()

    @patch.object(TmuxMessageDelivery, 'send_to_pane')
    def test_send_message_rate_limit(self, mock_send):
        """Test rate limiting in message sending."""
        mock_send.return_value = True

        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test_messages.log"
            # Set very low rate limit
            system = MessagingSystem(
                log_file=log_file,
                rate_limit_messages=2,
                rate_limit_window=60
            )

            # Register agents
            agent1 = MockAgent(
                id="agent-1",
                pane_index="session:0.1",
                pid=12345,
                status="active",
                last_seen=datetime.now(),
                session_name="test"
            )
            agent2 = MockAgent(
                id="agent-2",
                pane_index="session:0.2",
                pid=12346,
                status="active",
                last_seen=datetime.now(),
                session_name="test"
            )
            system.register_mock_agent(agent1)
            system.register_mock_agent(agent2)

            # Send 2 messages (should succeed)
            result1 = system.send_message("agent-1", "agent-2", MessageType.INFO, "Msg 1")
            result2 = system.send_message("agent-1", "agent-2", MessageType.INFO, "Msg 2")

            assert result1 is not None
            assert result2 is not None

            # Third message should fail due to rate limit
            result3 = system.send_message("agent-1", "agent-2", MessageType.INFO, "Msg 3")
            assert result3 is None

    @patch.object(TmuxMessageDelivery, 'send_to_pane')
    def test_broadcast_message(self, mock_send):
        """Test broadcast messaging to multiple agents."""
        mock_send.return_value = True

        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test_messages.log"
            system = MessagingSystem(log_file=log_file)

            # Register 4 agents
            for i in range(4):
                agent = MockAgent(
                    id=f"agent-{i}",
                    pane_index=f"session:0.{i}",
                    pid=12345 + i,
                    status="active",
                    last_seen=datetime.now(),
                    session_name="test"
                )
                

            # Broadcast from agent-0
            results = system.broadcast_message(
                "agent-0",
                MessageType.INFO,
                "Broadcast message",
                exclude_self=True
            )

            # Should send to 3 agents (excluding self)
            assert len(results) == 3
            assert "agent-0" not in results
            assert all(results.values())  # All should succeed
            assert mock_send.call_count == 3

    @patch.object(TmuxMessageDelivery, 'send_to_pane')
    def test_broadcast_include_self(self, mock_send):
        """Test broadcast messaging including sender."""
        mock_send.return_value = True

        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test_messages.log"
            system = MessagingSystem(log_file=log_file)

            # Register 3 agents
            for i in range(3):
                agent = MockAgent(
                    id=f"agent-{i}",
                    pane_index=f"session:0.{i}",
                    pid=12345 + i,
                    status="active",
                    last_seen=datetime.now(),
                    session_name="test"
                )
                

            # Broadcast from agent-0, including self
            results = system.broadcast_message(
                "agent-0",
                MessageType.INFO,
                "Broadcast message",
                exclude_self=False
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
            recipients=["agent-2"]
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
            recipients=["agent-2"]
        )
        assert msg.content == unicode_content

    def test_escape_preserves_unicode(self):
        """Test escaping preserves unicode characters."""
        text = "Test 你好 🎉"
        escaped = TmuxMessageDelivery.escape_for_tmux(text)
        # Unicode should be preserved
        assert "你好" in escaped or "\\u" in escaped
        assert "🎉" in escaped or "\\u" in escaped


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])
