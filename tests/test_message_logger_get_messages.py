"""
Comprehensive tests for MessageLogger.get_messages_for_agent() method.

This test module covers:
- Retrieving messages for a specific agent
- Limit parameter functionality
- Empty message log handling
- Missing message log file handling
- Malformed JSON handling
- Filtering by agent_id

Author: Test Coverage Enhancement
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from claudeswarm.messaging import Message, MessageLogger, MessageType


class TestMessageLoggerGetMessagesForAgent:
    """Tests for MessageLogger.get_messages_for_agent() method."""

    def test_get_messages_for_specific_agent(self):
        """Test retrieving messages for a specific agent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test_messages.log"
            logger = MessageLogger(log_file)

            # Create and log multiple messages to different agents
            msg1 = Message(
                sender_id="agent-1",
                timestamp=datetime.now(),
                msg_type=MessageType.INFO,
                content="Message to agent-2",
                recipients=["agent-2"]
            )
            msg2 = Message(
                sender_id="agent-3",
                timestamp=datetime.now(),
                msg_type=MessageType.QUESTION,
                content="Question for agent-2",
                recipients=["agent-2"]
            )
            msg3 = Message(
                sender_id="agent-1",
                timestamp=datetime.now(),
                msg_type=MessageType.INFO,
                content="Message to agent-4",
                recipients=["agent-4"]
            )

            logger.log_message(msg1, {"agent-2": True})
            logger.log_message(msg2, {"agent-2": True})
            logger.log_message(msg3, {"agent-4": True})

            # Get messages for agent-2
            messages = logger.get_messages_for_agent("agent-2")

            # Should have 2 messages for agent-2
            assert len(messages) == 2
            assert all(
                "agent-2" in msg.get("recipients", [])
                for msg in messages
            )

    def test_get_messages_with_limit(self):
        """Test limit parameter works correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test_messages.log"
            logger = MessageLogger(log_file)

            # Create and log 5 messages to the same agent
            for i in range(5):
                msg = Message(
                    sender_id=f"agent-{i}",
                    timestamp=datetime.now(),
                    msg_type=MessageType.INFO,
                    content=f"Message {i}",
                    recipients=["agent-target"]
                )
                logger.log_message(msg, {"agent-target": True})

            # Get messages with limit of 3
            messages = logger.get_messages_for_agent("agent-target", limit=3)

            # Should return only the 3 most recent messages
            assert len(messages) == 3

            # Verify they are the most recent ones (messages 2, 3, 4)
            contents = [msg["content"] for msg in messages]
            assert "Message 2" in contents
            assert "Message 3" in contents
            assert "Message 4" in contents
            assert "Message 0" not in contents
            assert "Message 1" not in contents

    def test_get_messages_with_no_limit(self):
        """Test getting all messages when limit is None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test_messages.log"
            logger = MessageLogger(log_file)

            # Create 10 messages
            for i in range(10):
                msg = Message(
                    sender_id=f"agent-{i}",
                    timestamp=datetime.now(),
                    msg_type=MessageType.INFO,
                    content=f"Message {i}",
                    recipients=["agent-target"]
                )
                logger.log_message(msg, {"agent-target": True})

            # Get all messages (no limit)
            messages = logger.get_messages_for_agent("agent-target", limit=None)

            # Should return all 10 messages
            assert len(messages) == 10

    def test_get_messages_with_zero_limit(self):
        """Test limit=0 returns all messages."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test_messages.log"
            logger = MessageLogger(log_file)

            # Create 3 messages
            for i in range(3):
                msg = Message(
                    sender_id=f"agent-{i}",
                    timestamp=datetime.now(),
                    msg_type=MessageType.INFO,
                    content=f"Message {i}",
                    recipients=["agent-target"]
                )
                logger.log_message(msg, {"agent-target": True})

            # Get messages with limit=0 (should return all)
            messages = logger.get_messages_for_agent("agent-target", limit=0)

            # Should return all messages when limit is 0 or None
            assert len(messages) == 3

    def test_get_messages_from_empty_log(self):
        """Test with empty message log."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test_messages.log"
            logger = MessageLogger(log_file)

            # Log file exists but is empty
            messages = logger.get_messages_for_agent("agent-1")

            # Should return empty list
            assert messages == []
            assert isinstance(messages, list)

    def test_get_messages_missing_log_file(self):
        """Test with missing message log file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "nonexistent_messages.log"
            logger = MessageLogger(log_file)

            # Delete the log file to simulate it not existing
            if log_file.exists():
                log_file.unlink()

            messages = logger.get_messages_for_agent("agent-1")

            # Should return empty list gracefully
            assert messages == []
            assert isinstance(messages, list)

    def test_get_messages_with_malformed_json(self):
        """Test with malformed JSON in log file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test_messages.log"
            logger = MessageLogger(log_file)

            # Write some valid and some invalid JSON lines
            with open(log_file, 'w') as f:
                # Valid message
                valid_msg = {
                    "sender": "agent-1",
                    "timestamp": datetime.now().isoformat(),
                    "msg_type": "INFO",
                    "content": "Valid message",
                    "recipients": ["agent-2"],
                    "msg_id": "test-1"
                }
                f.write(json.dumps(valid_msg) + '\n')

                # Invalid JSON (syntax error)
                f.write('{ "sender": "agent-2", "invalid json\n')

                # Another valid message
                valid_msg2 = {
                    "sender": "agent-3",
                    "timestamp": datetime.now().isoformat(),
                    "msg_type": "QUESTION",
                    "content": "Another valid message",
                    "recipients": ["agent-2"],
                    "msg_id": "test-2"
                }
                f.write(json.dumps(valid_msg2) + '\n')

            # Get messages for agent-2
            messages = logger.get_messages_for_agent("agent-2")

            # Should skip invalid JSON and return only valid messages
            assert len(messages) == 2
            assert messages[0]["content"] == "Valid message"
            assert messages[1]["content"] == "Another valid message"

    def test_get_messages_filtering_by_agent_id(self):
        """Test filtering by agent_id works correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test_messages.log"
            logger = MessageLogger(log_file)

            # Create messages to different agents
            agents = ["agent-1", "agent-2", "agent-3"]
            for i, recipient in enumerate(agents):
                msg = Message(
                    sender_id=f"sender-{i}",
                    timestamp=datetime.now(),
                    msg_type=MessageType.INFO,
                    content=f"Message for {recipient}",
                    recipients=[recipient]
                )
                logger.log_message(msg, {recipient: True})

            # Get messages for each agent separately
            for agent in agents:
                messages = logger.get_messages_for_agent(agent)
                assert len(messages) == 1
                assert messages[0]["recipients"] == [agent]

    def test_get_messages_for_nonexistent_agent(self):
        """Test getting messages for an agent with no messages."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test_messages.log"
            logger = MessageLogger(log_file)

            # Log messages for agent-1
            msg = Message(
                sender_id="agent-0",
                timestamp=datetime.now(),
                msg_type=MessageType.INFO,
                content="Message for agent-1",
                recipients=["agent-1"]
            )
            logger.log_message(msg, {"agent-1": True})

            # Try to get messages for agent-999 (doesn't have any)
            messages = logger.get_messages_for_agent("agent-999")

            # Should return empty list
            assert messages == []

    def test_get_messages_with_broadcast_all(self):
        """Test getting messages when recipient list contains 'all'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test_messages.log"
            logger = MessageLogger(log_file)

            # Create a broadcast message to 'all'
            msg = Message(
                sender_id="agent-0",
                timestamp=datetime.now(),
                msg_type=MessageType.INFO,
                content="Broadcast to all",
                recipients=["all"]
            )
            logger.log_message(msg, {"all": True})

            # Any agent should receive the 'all' broadcast
            for agent_id in ["agent-1", "agent-2", "agent-3"]:
                messages = logger.get_messages_for_agent(agent_id)
                assert len(messages) == 1
                assert "all" in messages[0]["recipients"]

    def test_get_messages_preserves_order(self):
        """Test that messages are returned in chronological order."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test_messages.log"
            logger = MessageLogger(log_file)

            # Create messages in specific order
            for i in range(5):
                msg = Message(
                    sender_id=f"agent-{i}",
                    timestamp=datetime.now(),
                    msg_type=MessageType.INFO,
                    content=f"Message {i}",
                    recipients=["agent-target"]
                )
                logger.log_message(msg, {"agent-target": True})

            messages = logger.get_messages_for_agent("agent-target")

            # Verify order is preserved
            for i, msg in enumerate(messages):
                assert f"Message {i}" in msg["content"]

    def test_get_messages_with_multiple_recipients(self):
        """Test messages with multiple recipients are correctly filtered."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test_messages.log"
            logger = MessageLogger(log_file)

            # Create a message to multiple recipients
            msg = Message(
                sender_id="agent-0",
                timestamp=datetime.now(),
                msg_type=MessageType.INFO,
                content="Message to multiple agents",
                recipients=["agent-1", "agent-2", "agent-3"]
            )
            logger.log_message(msg, {"agent-1": True, "agent-2": True, "agent-3": True})

            # Each recipient should see the message
            for agent_id in ["agent-1", "agent-2", "agent-3"]:
                messages = logger.get_messages_for_agent(agent_id)
                assert len(messages) == 1
                assert agent_id in messages[0]["recipients"]

    def test_get_messages_handles_empty_lines(self):
        """Test that empty lines in log file are handled correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test_messages.log"
            logger = MessageLogger(log_file)

            # Write messages with empty lines
            with open(log_file, 'w') as f:
                msg1 = {
                    "sender": "agent-1",
                    "timestamp": datetime.now().isoformat(),
                    "msg_type": "INFO",
                    "content": "First message",
                    "recipients": ["agent-2"],
                    "msg_id": "test-1"
                }
                f.write(json.dumps(msg1) + '\n')
                f.write('\n')  # Empty line
                f.write('   \n')  # Whitespace line
                msg2 = {
                    "sender": "agent-3",
                    "timestamp": datetime.now().isoformat(),
                    "msg_type": "INFO",
                    "content": "Second message",
                    "recipients": ["agent-2"],
                    "msg_id": "test-2"
                }
                f.write(json.dumps(msg2) + '\n')

            messages = logger.get_messages_for_agent("agent-2")

            # Should skip empty lines and return valid messages
            assert len(messages) == 2

    def test_get_messages_returns_expected_fields(self):
        """Test that returned messages contain all expected fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test_messages.log"
            logger = MessageLogger(log_file)

            msg = Message(
                sender_id="agent-1",
                timestamp=datetime.now(),
                msg_type=MessageType.QUESTION,
                content="Test message",
                recipients=["agent-2"]
            )
            logger.log_message(msg, {"agent-2": True})

            messages = logger.get_messages_for_agent("agent-2")

            assert len(messages) == 1
            message = messages[0]

            # Verify all expected fields are present
            assert "sender" in message
            assert "timestamp" in message
            assert "msg_type" in message
            assert "content" in message
            assert "recipients" in message
            assert "msg_id" in message

            # Verify field values
            assert message["sender"] == "agent-1"
            assert message["msg_type"] == "QUESTION"
            assert message["content"] == "Test message"
            assert message["recipients"] == ["agent-2"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
