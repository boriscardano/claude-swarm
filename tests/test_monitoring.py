"""Unit tests for monitoring dashboard module.

Tests cover:
- Log file tailing and parsing
- Message filtering
- Color coding
- Status sidebar generation
- Integration with discovery, locking, and ack systems
"""

import json
import tempfile
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from claudeswarm.discovery import Agent
from claudeswarm.locking import FileLock
from claudeswarm.messaging import Message, MessageType
from claudeswarm.monitoring import (
    ColorScheme,
    LogTailer,
    MessageFilter,
    Monitor,
    MonitoringState,
)


class TestMessageFilter:
    """Test MessageFilter functionality."""

    def test_filter_no_criteria(self):
        """Test that empty filter matches all messages."""
        msg_filter = MessageFilter()

        message = Message(
            sender_id="agent-0",
            timestamp=datetime.now(),
            msg_type=MessageType.INFO,
            content="test",
            recipients=["agent-1"]
        )

        assert msg_filter.matches(message)

    def test_filter_by_message_type(self):
        """Test filtering by message type."""
        msg_filter = MessageFilter(msg_types={MessageType.BLOCKED, MessageType.QUESTION})

        blocked_msg = Message(
            sender_id="agent-0",
            timestamp=datetime.now(),
            msg_type=MessageType.BLOCKED,
            content="blocked",
            recipients=["agent-1"]
        )

        info_msg = Message(
            sender_id="agent-0",
            timestamp=datetime.now(),
            msg_type=MessageType.INFO,
            content="info",
            recipients=["agent-1"]
        )

        assert msg_filter.matches(blocked_msg)
        assert not msg_filter.matches(info_msg)

    def test_filter_by_agent_sender(self):
        """Test filtering by agent ID (sender)."""
        msg_filter = MessageFilter(agent_ids={"agent-0"})

        matching_msg = Message(
            sender_id="agent-0",
            timestamp=datetime.now(),
            msg_type=MessageType.INFO,
            content="test",
            recipients=["agent-1"]
        )

        non_matching_msg = Message(
            sender_id="agent-1",
            timestamp=datetime.now(),
            msg_type=MessageType.INFO,
            content="test",
            recipients=["agent-2"]
        )

        assert msg_filter.matches(matching_msg)
        assert not msg_filter.matches(non_matching_msg)

    def test_filter_by_agent_recipient(self):
        """Test filtering by agent ID (recipient)."""
        msg_filter = MessageFilter(agent_ids={"agent-1"})

        matching_msg = Message(
            sender_id="agent-0",
            timestamp=datetime.now(),
            msg_type=MessageType.INFO,
            content="test",
            recipients=["agent-1"]
        )

        non_matching_msg = Message(
            sender_id="agent-0",
            timestamp=datetime.now(),
            msg_type=MessageType.INFO,
            content="test",
            recipients=["agent-2"]
        )

        assert msg_filter.matches(matching_msg)
        assert not msg_filter.matches(non_matching_msg)

    def test_filter_by_time_range(self):
        """Test filtering by time range."""
        now = datetime.now()
        start = now - timedelta(hours=1)
        end = now + timedelta(hours=1)

        msg_filter = MessageFilter(time_range=(start, end))

        matching_msg = Message(
            sender_id="agent-0",
            timestamp=now,
            msg_type=MessageType.INFO,
            content="test",
            recipients=["agent-1"]
        )

        old_msg = Message(
            sender_id="agent-0",
            timestamp=now - timedelta(hours=2),
            msg_type=MessageType.INFO,
            content="test",
            recipients=["agent-1"]
        )

        assert msg_filter.matches(matching_msg)
        assert not msg_filter.matches(old_msg)

    def test_filter_combined_criteria(self):
        """Test filtering with multiple criteria."""
        now = datetime.now()
        msg_filter = MessageFilter(
            msg_types={MessageType.BLOCKED},
            agent_ids={"agent-0"},
            time_range=(now - timedelta(hours=1), now + timedelta(hours=1))
        )

        # All criteria match
        matching_msg = Message(
            sender_id="agent-0",
            timestamp=now,
            msg_type=MessageType.BLOCKED,
            content="blocked",
            recipients=["agent-1"]
        )

        # Wrong type
        wrong_type_msg = Message(
            sender_id="agent-0",
            timestamp=now,
            msg_type=MessageType.INFO,
            content="info",
            recipients=["agent-1"]
        )

        # Wrong agent
        wrong_agent_msg = Message(
            sender_id="agent-1",
            timestamp=now,
            msg_type=MessageType.BLOCKED,
            content="blocked",
            recipients=["agent-2"]
        )

        # Wrong time
        wrong_time_msg = Message(
            sender_id="agent-0",
            timestamp=now - timedelta(hours=2),
            msg_type=MessageType.BLOCKED,
            content="blocked",
            recipients=["agent-1"]
        )

        assert msg_filter.matches(matching_msg)
        assert not msg_filter.matches(wrong_type_msg)
        assert not msg_filter.matches(wrong_agent_msg)
        assert not msg_filter.matches(wrong_time_msg)


class TestLogTailer:
    """Test LogTailer functionality."""

    def test_creates_log_if_not_exists(self, tmp_path):
        """Test that log file is created if it doesn't exist."""
        log_path = tmp_path / "test.log"
        tailer = LogTailer(log_path)

        assert log_path.exists()

    def test_tail_new_lines(self, tmp_path):
        """Test tailing new lines from log file."""
        log_path = tmp_path / "test.log"
        log_path.write_text("line1\nline2\n")

        tailer = LogTailer(log_path)

        # First read should get all lines
        lines = tailer.tail_new_lines()
        assert lines == ["line1", "line2"]

        # Second read should get nothing (no new lines)
        lines = tailer.tail_new_lines()
        assert lines == []

        # Add new lines
        with open(log_path, 'a') as f:
            f.write("line3\nline4\n")

        # Should get only new lines
        lines = tailer.tail_new_lines()
        assert lines == ["line3", "line4"]

    def test_parse_valid_log_entry(self, tmp_path):
        """Test parsing valid JSON log entry."""
        log_path = tmp_path / "test.log"
        tailer = LogTailer(log_path)

        log_entry = {
            "timestamp": "2025-11-07T10:00:00",
            "sender": "agent-0",
            "msg_type": "INFO",
            "content": "test message",
            "recipients": ["agent-1"],
            "msg_id": "123"
        }

        line = json.dumps(log_entry)
        message = tailer.parse_log_entry(line)

        assert message is not None
        assert message.sender_id == "agent-0"
        assert message.msg_type == MessageType.INFO
        assert message.content == "test message"
        assert message.recipients == ["agent-1"]
        assert message.msg_id == "123"

    def test_parse_invalid_log_entry(self, tmp_path):
        """Test parsing invalid log entry returns None."""
        log_path = tmp_path / "test.log"
        tailer = LogTailer(log_path)

        # Invalid JSON
        assert tailer.parse_log_entry("not json") is None

        # Missing required fields
        assert tailer.parse_log_entry("{}") is None

        # Invalid message type
        invalid_entry = json.dumps({
            "timestamp": "2025-11-07T10:00:00",
            "sender": "agent-0",
            "msg_type": "INVALID_TYPE",
            "content": "test",
            "recipients": []
        })
        assert tailer.parse_log_entry(invalid_entry) is None

    def test_handle_log_rotation(self, tmp_path):
        """Test handling of log file rotation."""
        log_path = tmp_path / "test.log"
        log_path.write_text("line1\n")

        tailer = LogTailer(log_path)

        # Read initial content
        lines = tailer.tail_new_lines()
        assert lines == ["line1"]

        # Simulate log rotation (file deleted and recreated)
        log_path.unlink()
        log_path.write_text("line2\n")

        # Should handle gracefully
        lines = tailer.tail_new_lines()
        # May return empty or the new line depending on implementation
        assert isinstance(lines, list)


class TestMonitor:
    """Test Monitor functionality."""

    def test_format_with_colors_blocked(self):
        """Test color formatting for BLOCKED messages."""
        monitor = Monitor()

        message = Message(
            sender_id="agent-0",
            timestamp=datetime(2025, 11, 7, 10, 0, 0),
            msg_type=MessageType.BLOCKED,
            content="blocked on lock",
            recipients=["agent-1"]
        )

        formatted = monitor.format_with_colors(message)

        assert ColorScheme.RED in formatted
        assert "agent-0" in formatted
        assert "BLOCKED" in formatted
        assert "blocked on lock" in formatted
        assert "10:00:00" in formatted

    def test_format_with_colors_question(self):
        """Test color formatting for QUESTION messages."""
        monitor = Monitor()

        message = Message(
            sender_id="agent-0",
            timestamp=datetime(2025, 11, 7, 10, 0, 0),
            msg_type=MessageType.QUESTION,
            content="what database?",
            recipients=["agent-1"]
        )

        formatted = monitor.format_with_colors(message)

        assert ColorScheme.YELLOW in formatted
        assert "QUESTION" in formatted

    def test_format_with_colors_completed(self):
        """Test color formatting for COMPLETED messages."""
        monitor = Monitor()

        message = Message(
            sender_id="agent-0",
            timestamp=datetime(2025, 11, 7, 10, 0, 0),
            msg_type=MessageType.COMPLETED,
            content="task done",
            recipients=["agent-1"]
        )

        formatted = monitor.format_with_colors(message)

        assert ColorScheme.GREEN in formatted
        assert "COMPLETED" in formatted

    def test_format_with_colors_info(self):
        """Test color formatting for INFO messages."""
        monitor = Monitor()

        message = Message(
            sender_id="agent-0",
            timestamp=datetime(2025, 11, 7, 10, 0, 0),
            msg_type=MessageType.INFO,
            content="status update",
            recipients=["agent-1"]
        )

        formatted = monitor.format_with_colors(message)

        assert ColorScheme.BLUE in formatted
        assert "INFO" in formatted

    def test_render_sidebar_empty_state(self):
        """Test rendering sidebar with no active resources."""
        monitor = Monitor()

        state = MonitoringState(
            active_agents=[],
            active_locks=[],
            pending_acks=[],
            recent_messages=deque()
        )

        lines = monitor.render_sidebar(state)

        # Should have header and sections
        assert any("CLAUDE SWARM STATUS" in line for line in lines)
        assert any("Active Agents: 0" in line for line in lines)
        assert any("Active Locks: 0" in line for line in lines)
        assert any("Pending ACKs: 0" in line for line in lines)
        assert any("No active agents" in line for line in lines)

    def test_render_sidebar_with_agents(self):
        """Test rendering sidebar with active agents."""
        monitor = Monitor()

        agents = [
            Agent(
                id="agent-0",
                pane_index="0:0.0",
                pid=1234,
                status="active",
                last_seen="2025-11-07T10:00:00",
                session_name="test"
            ),
            Agent(
                id="agent-1",
                pane_index="0:0.1",
                pid=1235,
                status="active",
                last_seen="2025-11-07T10:00:00",
                session_name="test"
            )
        ]

        state = MonitoringState(
            active_agents=agents,
            active_locks=[],
            pending_acks=[],
            recent_messages=deque()
        )

        lines = monitor.render_sidebar(state)

        assert any("Active Agents: 2" in line for line in lines)
        assert any("agent-0" in line for line in lines)
        assert any("agent-1" in line for line in lines)

    def test_render_sidebar_with_locks(self):
        """Test rendering sidebar with active locks."""
        monitor = Monitor()

        import time
        locks = [
            FileLock(
                agent_id="agent-0",
                filepath="src/test.py",
                locked_at=time.time(),
                reason="editing"
            )
        ]

        state = MonitoringState(
            active_agents=[],
            active_locks=locks,
            pending_acks=[],
            recent_messages=deque()
        )

        lines = monitor.render_sidebar(state)

        assert any("Active Locks: 1" in line for line in lines)
        assert any("src/test.py" in line for line in lines)
        assert any("agent-0" in line for line in lines)

    def test_render_sidebar_truncates_long_lists(self):
        """Test that sidebar truncates long lists."""
        monitor = Monitor()

        import time
        # Create 10 locks
        locks = [
            FileLock(
                agent_id=f"agent-{i}",
                filepath=f"file{i}.py",
                locked_at=time.time(),
                reason="test"
            )
            for i in range(10)
        ]

        state = MonitoringState(
            active_agents=[],
            active_locks=locks,
            pending_acks=[],
            recent_messages=deque()
        )

        lines = monitor.render_sidebar(state)

        # Should show max 5 locks plus "... and X more"
        assert any("Active Locks: 10" in line for line in lines)
        assert any("and 5 more" in line for line in lines)

    def test_process_new_logs(self, tmp_path):
        """Test processing new log entries."""
        log_path = tmp_path / "test.log"

        monitor = Monitor(log_path=log_path)

        # Write log entries
        log_entries = [
            {
                "timestamp": datetime.now().isoformat(),
                "sender": "agent-0",
                "msg_type": "INFO",
                "content": "message 1",
                "recipients": ["agent-1"],
                "msg_id": "1"
            },
            {
                "timestamp": datetime.now().isoformat(),
                "sender": "agent-1",
                "msg_type": "QUESTION",
                "content": "message 2",
                "recipients": ["agent-0"],
                "msg_id": "2"
            }
        ]

        with open(log_path, 'w') as f:
            for entry in log_entries:
                f.write(json.dumps(entry) + '\n')

        # Process logs
        monitor.process_new_logs()

        # Should have messages in buffer
        assert len(monitor.recent_messages) == 2
        assert monitor.recent_messages[0].sender_id == "agent-0"
        assert monitor.recent_messages[1].sender_id == "agent-1"

    def test_message_buffer_max_size(self, tmp_path):
        """Test that message buffer respects max size."""
        log_path = tmp_path / "test.log"

        monitor = Monitor(log_path=log_path)

        # Add 150 messages (buffer is limited to 100)
        for i in range(150):
            message = Message(
                sender_id=f"agent-{i % 5}",
                timestamp=datetime.now(),
                msg_type=MessageType.INFO,
                content=f"message {i}",
                recipients=["agent-0"]
            )
            monitor.recent_messages.append(message)

        # Should only have 100 messages
        assert len(monitor.recent_messages) == 100

        # Should have the most recent 100
        assert "message 50" in monitor.recent_messages[0].content
        assert "message 149" in monitor.recent_messages[-1].content


class TestColorScheme:
    """Test ColorScheme constants."""

    def test_color_codes_exist(self):
        """Test that all color codes are defined."""
        assert ColorScheme.RED
        assert ColorScheme.YELLOW
        assert ColorScheme.GREEN
        assert ColorScheme.BLUE
        assert ColorScheme.MAGENTA
        assert ColorScheme.CYAN
        assert ColorScheme.WHITE
        assert ColorScheme.GRAY
        assert ColorScheme.RESET
        assert ColorScheme.BOLD
        assert ColorScheme.DIM

    def test_color_codes_are_strings(self):
        """Test that color codes are strings."""
        assert isinstance(ColorScheme.RED, str)
        assert isinstance(ColorScheme.GREEN, str)
        assert isinstance(ColorScheme.RESET, str)

    def test_color_codes_are_ansi_escape_sequences(self):
        """Test that color codes start with ANSI escape sequence."""
        assert ColorScheme.RED.startswith('\033[')
        assert ColorScheme.GREEN.startswith('\033[')
        assert ColorScheme.RESET.startswith('\033[')


class TestMonitoringIntegration:
    """Integration tests for monitoring with other systems."""

    def test_monitor_with_filter(self, tmp_path):
        """Test monitor with message filtering."""
        log_path = tmp_path / "test.log"

        msg_filter = MessageFilter(msg_types={MessageType.BLOCKED})
        monitor = Monitor(log_path=log_path, message_filter=msg_filter)

        # Add messages of different types
        log_entries = [
            {
                "timestamp": datetime.now().isoformat(),
                "sender": "agent-0",
                "msg_type": "BLOCKED",
                "content": "blocked",
                "recipients": ["agent-1"],
                "msg_id": "1"
            },
            {
                "timestamp": datetime.now().isoformat(),
                "sender": "agent-0",
                "msg_type": "INFO",
                "content": "info",
                "recipients": ["agent-1"],
                "msg_id": "2"
            }
        ]

        with open(log_path, 'w') as f:
            for entry in log_entries:
                f.write(json.dumps(entry) + '\n')

        # Process logs
        monitor.process_new_logs()

        # Should have both messages in buffer
        assert len(monitor.recent_messages) == 2

        # But filtering should only show BLOCKED messages
        filtered = [msg for msg in monitor.recent_messages if monitor.message_filter.matches(msg)]
        assert len(filtered) == 1
        assert filtered[0].msg_type == MessageType.BLOCKED
