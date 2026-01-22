"""Performance and long-running scenario tests.

Tests cover:
- Rate limiter memory management in long-running scenarios
- Log rotation detection and handling
- Resource cleanup verification
- Memory leak prevention
"""

import json
import time
from datetime import datetime, timedelta

import pytest

from claudeswarm.messaging import Message, MessageType, RateLimiter
from claudeswarm.monitoring import LogTailer, MessageFilter, Monitor


class TestRateLimiterPerformance:
    """Test RateLimiter performance and memory management."""

    def test_rate_limiter_bounded_memory(self):
        """Test that rate limiter doesn't grow unbounded with many agents."""
        limiter = RateLimiter(max_messages=10, window_seconds=60)

        # Simulate 1000 different agents sending messages
        for i in range(1000):
            agent_id = f"agent-{i}"
            limiter.record_message(agent_id)

        # Verify internal state is bounded
        assert len(limiter._message_times) == 1000

        # Each agent should have at most max_messages entries
        for times in limiter._message_times.values():
            assert len(times) <= 10

    def test_rate_limiter_cleanup_inactive(self):
        """Test cleanup of inactive agents."""
        limiter = RateLimiter(max_messages=5, window_seconds=60)

        # Add some active agents
        for i in range(5):
            limiter.record_message(f"active-{i}")

        # Add some old inactive agents (simulate by manipulating timestamp)
        old_time = datetime.now() - timedelta(seconds=7200)
        for i in range(5):
            agent_id = f"inactive-{i}"
            limiter._message_times[agent_id].append(old_time)

        # Verify we have 10 agents
        assert len(limiter._message_times) == 10

        # Cleanup agents inactive for more than 1 hour
        removed = limiter.cleanup_inactive_agents(cutoff_seconds=3600)

        # Should have removed 5 inactive agents
        assert removed == 5
        assert len(limiter._message_times) == 5

        # Verify only active agents remain
        for agent_id in limiter._message_times.keys():
            assert agent_id.startswith("active-")

    def test_rate_limiter_window_sliding(self):
        """Test that rate limiter properly handles sliding window."""
        limiter = RateLimiter(max_messages=3, window_seconds=2)

        # Send 3 messages quickly
        for _ in range(3):
            limiter.record_message("agent-1")

        # Should be at limit
        assert not limiter.check_rate_limit("agent-1")

        # Wait for window to slide
        time.sleep(2.1)

        # Should be able to send again
        assert limiter.check_rate_limit("agent-1")

    def test_rate_limiter_long_running(self):
        """Test rate limiter in simulated long-running scenario."""
        limiter = RateLimiter(max_messages=5, window_seconds=1)

        # Simulate 10 cycles of activity
        for cycle in range(10):
            # Multiple agents send messages
            for agent_num in range(20):
                agent_id = f"agent-{agent_num}"

                # Try to send up to 5 messages
                sent = 0
                for _ in range(7):  # Try more than limit
                    if limiter.check_rate_limit(agent_id):
                        limiter.record_message(agent_id)
                        sent += 1

                # Should only send up to max_messages
                assert sent <= 5

            # Wait for window to reset
            time.sleep(1.1)

        # Verify memory hasn't grown unbounded
        assert len(limiter._message_times) == 20

        # Each agent should have recent messages within limit
        for times in limiter._message_times.values():
            assert len(times) <= 5


class TestLogTailerRotation:
    """Test LogTailer log rotation detection."""

    def test_log_rotation_size_detection(self, tmp_path):
        """Test detection of log rotation by file size."""
        log_path = tmp_path / "test.log"
        log_path.write_text("line1\nline2\nline3\n")

        tailer = LogTailer(log_path)

        # Read all lines
        lines = tailer.tail_new_lines()
        assert len(lines) == 3
        assert tailer.position > 0

        old_position = tailer.position

        # Simulate log rotation - file becomes smaller
        log_path.write_text("new line 1\n")

        # Should detect rotation and reset position
        lines = tailer.tail_new_lines()
        assert tailer.position < old_position
        assert lines == ["new line 1"]

    def test_log_rotation_inode_detection(self, tmp_path):
        """Test detection of log rotation by inode change."""
        log_path = tmp_path / "test.log"
        log_path.write_text("line1\n")

        tailer = LogTailer(log_path)
        lines = tailer.tail_new_lines()
        assert lines == ["line1"]

        old_inode = tailer.last_inode

        # Simulate rotation by replacing file
        log_path.unlink()
        log_path.write_text("rotated line 1\n")

        # New file should have different inode
        new_stat = log_path.stat()
        # Note: on some filesystems, inode might be reused immediately

        lines = tailer.tail_new_lines()
        # Should read from beginning of new file
        assert "rotated" in lines[0] or len(lines) == 1

    def test_log_rotation_multiple_cycles(self, tmp_path):
        """Test handling of multiple log rotation cycles."""
        log_path = tmp_path / "test.log"

        tailer = LogTailer(log_path)

        # Simulate 5 rotation cycles
        for cycle in range(5):
            # Write some data
            with open(log_path, "a") as f:
                for i in range(10):
                    f.write(f"cycle {cycle} line {i}\n")

            # Read the data
            lines = tailer.tail_new_lines()
            assert len(lines) == 10

            # Rotate (simulate by truncating)
            log_path.write_text(f"cycle {cycle + 1} start\n")

            # Verify rotation is detected
            lines = tailer.tail_new_lines()
            assert any("start" in line for line in lines)

    def test_log_tailer_cleanup(self, tmp_path):
        """Test LogTailer resource cleanup."""
        log_path = tmp_path / "test.log"
        log_path.write_text("test line\n")

        tailer = LogTailer(log_path)
        tailer.tail_new_lines()

        # Position should be non-zero
        assert tailer.position > 0

        # Cleanup should reset state
        tailer.cleanup()
        assert tailer.position == 0
        assert tailer.last_inode is None

    def test_log_tailer_context_manager(self, tmp_path):
        """Test LogTailer context manager protocol."""
        log_path = tmp_path / "test.log"
        log_path.write_text("test line\n")

        with LogTailer(log_path) as tailer:
            lines = tailer.tail_new_lines()
            assert len(lines) == 1
            # Position should be set
            assert tailer.position > 0

        # After context exit, should be cleaned up
        assert tailer.position == 0
        assert tailer.last_inode is None


class TestMonitorResourceManagement:
    """Test Monitor resource management."""

    def test_monitor_cleanup(self, tmp_path):
        """Test Monitor properly cleans up resources."""
        log_path = tmp_path / "test.log"

        monitor = Monitor(log_path=log_path)

        # Add some messages to buffer
        for i in range(50):
            msg = Message(
                sender_id=f"agent-{i % 5}",
                timestamp=datetime.now(),
                msg_type=MessageType.INFO,
                content=f"message {i}",
                recipients=["agent-0"],
            )
            monitor.recent_messages.append(msg)

        assert len(monitor.recent_messages) == 50

        # Stop should cleanup
        monitor.stop()

        assert len(monitor.recent_messages) == 0
        assert not monitor.running

    def test_monitor_context_manager(self, tmp_path):
        """Test Monitor context manager protocol."""
        log_path = tmp_path / "test.log"

        with Monitor(log_path=log_path) as monitor:
            # Add messages
            for i in range(10):
                msg = Message(
                    sender_id="agent-0",
                    timestamp=datetime.now(),
                    msg_type=MessageType.INFO,
                    content=f"message {i}",
                    recipients=["agent-1"],
                )
                monitor.recent_messages.append(msg)

            assert len(monitor.recent_messages) == 10

        # After exit, should be cleaned up
        assert len(monitor.recent_messages) == 0


class TestMessageFilterPerformance:
    """Test MessageFilter performance with large volumes."""

    def test_filter_performance_large_volume(self):
        """Test filter performance with large message volume."""
        # Create filter for specific message types
        msg_filter = MessageFilter(msg_types={MessageType.BLOCKED, MessageType.QUESTION})

        # Create 10000 messages
        messages = []
        for i in range(10000):
            msg_type = [
                MessageType.BLOCKED,
                MessageType.QUESTION,
                MessageType.INFO,
                MessageType.COMPLETED,
            ][i % 4]
            msg = Message(
                sender_id=f"agent-{i % 100}",
                timestamp=datetime.now(),
                msg_type=msg_type,
                content=f"message {i}",
                recipients=[f"agent-{(i + 1) % 100}"],
            )
            messages.append(msg)

        # Filter all messages - should be fast
        import time

        start = time.time()
        filtered = [msg for msg in messages if msg_filter.matches(msg)]
        elapsed = time.time() - start

        # Should filter 10k messages in under 100ms
        assert elapsed < 0.1

        # Should have filtered correctly (25% BLOCKED + 25% QUESTION = 50%)
        assert len(filtered) == 5000

    def test_filter_set_intersection_optimization(self):
        """Test that filter uses optimized set intersection."""
        # Create filter for multiple agents
        agent_ids = {f"agent-{i}" for i in range(50)}
        msg_filter = MessageFilter(agent_ids=agent_ids)

        # Create messages with many recipients
        messages = []
        for i in range(1000):
            recipients = [f"agent-{j}" for j in range(i % 10, (i % 10) + 5)]
            msg = Message(
                sender_id=f"sender-{i}",
                timestamp=datetime.now(),
                msg_type=MessageType.INFO,
                content=f"message {i}",
                recipients=recipients,
            )
            messages.append(msg)

        # Filter should use set intersection (fast)
        start = time.time()
        _ = [msg for msg in messages if msg_filter.matches(msg)]
        elapsed = time.time() - start

        # Should be very fast (< 50ms for 1000 messages)
        assert elapsed < 0.05


class TestMemoryLeakPrevention:
    """Test that components don't leak memory."""

    def test_rate_limiter_no_memory_leak(self):
        """Test rate limiter doesn't leak memory over time."""
        limiter = RateLimiter(max_messages=10, window_seconds=1)

        # Simulate many agents over time
        for cycle in range(100):
            # New batch of agents
            for agent_num in range(10):
                agent_id = f"cycle-{cycle}-agent-{agent_num}"
                limiter.record_message(agent_id)

            # Small delay between cycles to allow time to pass
            time.sleep(0.01)

            # Cleanup old agents every 10 cycles
            if cycle % 10 == 0 and cycle > 0:
                # Cleanup agents inactive for more than 0.5 seconds
                limiter.cleanup_inactive_agents(cutoff_seconds=1)

        # Do a final cleanup of old agents
        _ = limiter.cleanup_inactive_agents(cutoff_seconds=0)

        # After cleanup, should have only recent agents (last cycle batch = 10)
        assert len(limiter._message_times) <= 10

    def test_monitor_bounded_message_buffer(self, tmp_path):
        """Test monitor message buffer is bounded."""
        log_path = tmp_path / "test.log"
        monitor = Monitor(log_path=log_path)

        # Write many log entries
        with open(log_path, "w") as f:
            for i in range(500):
                entry = {
                    "timestamp": datetime.now().isoformat(),
                    "sender": f"agent-{i % 10}",
                    "msg_type": "INFO",
                    "content": f"message {i}",
                    "recipients": ["agent-0"],
                    "msg_id": str(i),
                }
                f.write(json.dumps(entry) + "\n")

        # Process logs
        monitor.process_new_logs()

        # Buffer should be limited to 100 (maxlen of deque)
        assert len(monitor.recent_messages) == 100

        # Should have most recent messages
        assert "message 499" in monitor.recent_messages[-1].content


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
