"""Comprehensive tests for claudeswarm.ack module.

Tests cover:
- ACK tracking and persistence
- Send-with-ack functionality
- ACK reception and matching
- Retry logic with exponential backoff
- Timeout calculation
- Escalation after max retries
- Integration with messaging system
"""

import json
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from claudeswarm.ack import (
    AckSystem,
    PendingAck,
    acknowledge_message,
    check_pending_acks,
    receive_ack,
    send_with_ack,
    process_pending_retries,
    get_ack_system,
)
from claudeswarm.messaging import Message, MessageType


class TestPendingAck:
    """Test PendingAck dataclass functionality."""

    def test_creation(self) -> None:
        """Test creating a PendingAck instance."""
        now = datetime.now()
        msg = Message(
            sender_id="agent-1",
            timestamp=now,
            msg_type=MessageType.QUESTION,
            content="Test message",
            recipients=["agent-2"],
        )

        ack = PendingAck(
            msg_id=msg.msg_id,
            sender_id="agent-1",
            recipient_id="agent-2",
            message=msg.to_dict(),
            sent_at=now.isoformat(),
            retry_count=0,
            next_retry_at=(now + timedelta(seconds=30)).isoformat(),
        )

        assert ack.msg_id == msg.msg_id
        assert ack.sender_id == "agent-1"
        assert ack.recipient_id == "agent-2"
        assert ack.retry_count == 0

    def test_to_dict_from_dict(self) -> None:
        """Test serialization and deserialization."""
        now = datetime.now()
        msg = Message(
            sender_id="agent-1",
            timestamp=now,
            msg_type=MessageType.QUESTION,
            content="Test",
            recipients=["agent-2"],
        )

        ack = PendingAck(
            msg_id=msg.msg_id,
            sender_id="agent-1",
            recipient_id="agent-2",
            message=msg.to_dict(),
            sent_at=now.isoformat(),
            retry_count=1,
            next_retry_at=(now + timedelta(seconds=60)).isoformat(),
        )

        # Serialize and deserialize
        ack_dict = ack.to_dict()
        restored = PendingAck.from_dict(ack_dict)

        assert restored.msg_id == ack.msg_id
        assert restored.sender_id == ack.sender_id
        assert restored.recipient_id == ack.recipient_id
        assert restored.retry_count == ack.retry_count

    def test_datetime_conversion(self) -> None:
        """Test datetime conversion methods."""
        now = datetime.now()
        next_retry = now + timedelta(seconds=30)

        ack = PendingAck(
            msg_id="test-id",
            sender_id="agent-1",
            recipient_id="agent-2",
            message={},
            sent_at=now.isoformat(),
            retry_count=0,
            next_retry_at=next_retry.isoformat(),
        )

        sent_dt = ack.get_sent_datetime()
        next_dt = ack.get_next_retry_datetime()

        assert abs((sent_dt - now).total_seconds()) < 1
        assert abs((next_dt - next_retry).total_seconds()) < 1


class TestAckSystem:
    """Test AckSystem class functionality."""

    @pytest.fixture
    def temp_dir(self) -> Path:
        """Create temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def ack_system(self, temp_dir: Path) -> AckSystem:
        """Create AckSystem instance with temporary file."""
        pending_file = temp_dir / "PENDING_ACKS.json"
        return AckSystem(pending_file=pending_file)

    def test_initialization(self, ack_system: AckSystem) -> None:
        """Test AckSystem initialization."""
        assert ack_system.pending_file.exists()

        # Check file contains empty list
        with open(ack_system.pending_file) as f:
            data = json.load(f)
        assert data == {"pending_acks": []}

    def test_ensure_pending_file_idempotent(self, ack_system: AckSystem) -> None:
        """Test that _ensure_pending_file is idempotent."""
        # Call multiple times
        ack_system._ensure_pending_file()
        ack_system._ensure_pending_file()

        # Should still have empty list
        with open(ack_system.pending_file) as f:
            data = json.load(f)
        assert data == {"pending_acks": []}

    @patch("claudeswarm.ack.send_message")
    def test_send_with_ack_success(
        self, mock_send: MagicMock, ack_system: AckSystem
    ) -> None:
        """Test sending a message with ACK requirement."""
        # Mock send_message to return a Message
        now = datetime.now()
        mock_msg = Message(
            sender_id="agent-1",
            timestamp=now,
            msg_type=MessageType.QUESTION,
            content="[REQUIRES-ACK] Test message",
            recipients=["agent-2"],
            msg_id="test-msg-id",
        )
        mock_send.return_value = mock_msg

        # Send with ACK
        msg_id = ack_system.send_with_ack(
            "agent-1", "agent-2", MessageType.QUESTION, "Test message", timeout=30
        )

        assert msg_id == "test-msg-id"

        # Verify send_message was called with [REQUIRES-ACK] prefix
        mock_send.assert_called_once_with(
            "agent-1", "agent-2", MessageType.QUESTION, "[REQUIRES-ACK] Test message"
        )

        # Verify pending ACK was added
        pending = ack_system.check_pending_acks()
        assert len(pending) == 1
        assert pending[0].msg_id == "test-msg-id"
        assert pending[0].sender_id == "agent-1"
        assert pending[0].recipient_id == "agent-2"

    @patch("claudeswarm.ack.send_message")
    def test_send_with_ack_failure(
        self, mock_send: MagicMock, ack_system: AckSystem
    ) -> None:
        """Test handling of send failure."""
        mock_send.return_value = None

        msg_id = ack_system.send_with_ack(
            "agent-1", "agent-2", MessageType.QUESTION, "Test"
        )

        assert msg_id is None

        # No pending ACKs should be added
        pending = ack_system.check_pending_acks()
        assert len(pending) == 0

    def test_send_with_ack_validation(self, ack_system: AckSystem) -> None:
        """Test validation of send_with_ack parameters."""
        # Our new validation provides more specific error messages
        with pytest.raises(ValueError, match="Invalid input"):
            ack_system.send_with_ack("", "agent-2", MessageType.QUESTION, "Test")

        with pytest.raises(ValueError, match="Invalid input"):
            ack_system.send_with_ack("agent-1", "", MessageType.QUESTION, "Test")

    def test_receive_ack_success(self, ack_system: AckSystem, temp_dir: Path) -> None:
        """Test receiving and matching ACK."""
        # Manually add a pending ACK
        now = datetime.now()
        msg = Message(
            sender_id="agent-1",
            timestamp=now,
            msg_type=MessageType.QUESTION,
            content="Test",
            recipients=["agent-2"],
            msg_id="test-msg-id",
        )

        ack = PendingAck(
            msg_id="test-msg-id",
            sender_id="agent-1",
            recipient_id="agent-2",
            message=msg.to_dict(),
            sent_at=now.isoformat(),
            retry_count=0,
            next_retry_at=(now + timedelta(seconds=30)).isoformat(),
        )

        ack_system._save_pending_acks([ack])

        # Receive ACK
        result = ack_system.receive_ack("test-msg-id", "agent-2")
        assert result is True

        # Verify ACK was removed
        pending = ack_system.check_pending_acks()
        assert len(pending) == 0

    def test_receive_ack_wrong_agent(self, ack_system: AckSystem) -> None:
        """Test receiving ACK from unexpected agent (should still accept)."""
        now = datetime.now()
        msg = Message(
            sender_id="agent-1",
            timestamp=now,
            msg_type=MessageType.QUESTION,
            content="Test",
            recipients=["agent-2"],
            msg_id="test-msg-id",
        )

        ack = PendingAck(
            msg_id="test-msg-id",
            sender_id="agent-1",
            recipient_id="agent-2",
            message=msg.to_dict(),
            sent_at=now.isoformat(),
            retry_count=0,
            next_retry_at=(now + timedelta(seconds=30)).isoformat(),
        )

        ack_system._save_pending_acks([ack])

        # ACK from different agent
        result = ack_system.receive_ack("test-msg-id", "agent-3")
        assert result is True  # Still accepts

        # Verify ACK was removed
        pending = ack_system.check_pending_acks()
        assert len(pending) == 0

    def test_receive_ack_not_found(self, ack_system: AckSystem) -> None:
        """Test receiving ACK for non-existent message."""
        result = ack_system.receive_ack("nonexistent-id", "agent-1")
        assert result is False

    def test_check_pending_acks_filter(self, ack_system: AckSystem) -> None:
        """Test filtering pending ACKs by agent."""
        now = datetime.now()

        # Add ACKs from different senders
        for i in range(3):
            msg = Message(
                sender_id=f"agent-{i}",
                timestamp=now,
                msg_type=MessageType.QUESTION,
                content=f"Test {i}",
                recipients=[f"agent-{i+1}"],
                msg_id=f"msg-{i}",
            )

            ack = PendingAck(
                msg_id=f"msg-{i}",
                sender_id=f"agent-{i}",
                recipient_id=f"agent-{i+1}",
                message=msg.to_dict(),
                sent_at=now.isoformat(),
                retry_count=0,
                next_retry_at=(now + timedelta(seconds=30)).isoformat(),
            )

            ack_system._save_pending_acks(ack_system._load_pending_acks() + [ack])

        # Check all
        all_pending = ack_system.check_pending_acks()
        assert len(all_pending) == 3

        # Filter by agent-1
        agent1_pending = ack_system.check_pending_acks("agent-1")
        assert len(agent1_pending) == 1
        assert agent1_pending[0].sender_id == "agent-1"

    @patch("claudeswarm.ack.send_message")
    def test_retry_mechanism(self, mock_send: MagicMock, ack_system: AckSystem) -> None:
        """Test retry mechanism with exponential backoff."""
        now = datetime.now()
        msg = Message(
            sender_id="agent-1",
            timestamp=now,
            msg_type=MessageType.QUESTION,
            content="[REQUIRES-ACK] Test",
            recipients=["agent-2"],
            msg_id="test-msg-id",
        )

        # Add pending ACK that's ready for retry
        past_time = now - timedelta(seconds=5)
        ack = PendingAck(
            msg_id="test-msg-id",
            sender_id="agent-1",
            recipient_id="agent-2",
            message=msg.to_dict(),
            sent_at=past_time.isoformat(),
            retry_count=0,
            next_retry_at=past_time.isoformat(),  # Already past
        )

        ack_system._save_pending_acks([ack])

        # Process retries
        count = ack_system.process_retries()
        assert count == 1

        # Verify send_message was called for retry
        mock_send.assert_called_once()
        args = mock_send.call_args[0]
        assert "[RETRY-1]" in args[3]

        # Verify retry count increased and next_retry_at updated
        pending = ack_system.check_pending_acks()
        assert len(pending) == 1
        assert pending[0].retry_count == 1

        # Next retry should be ~60 seconds in the future (2nd retry delay)
        next_retry_dt = pending[0].get_next_retry_datetime()
        expected_delay = timedelta(seconds=AckSystem.RETRY_DELAYS[1])
        assert abs((next_retry_dt - now) - expected_delay) < timedelta(seconds=2)

    @patch("claudeswarm.ack.send_message")
    @patch("claudeswarm.ack.broadcast_message")
    def test_escalation_after_max_retries(
        self, mock_broadcast: MagicMock, mock_send: MagicMock, ack_system: AckSystem
    ) -> None:
        """Test escalation after maximum retry attempts."""
        now = datetime.now()
        msg = Message(
            sender_id="agent-1",
            timestamp=now,
            msg_type=MessageType.QUESTION,
            content="Test",
            recipients=["agent-2"],
            msg_id="test-msg-id",
        )

        # Add pending ACK with MAX_RETRIES already done
        past_time = now - timedelta(seconds=5)
        ack = PendingAck(
            msg_id="test-msg-id",
            sender_id="agent-1",
            recipient_id="agent-2",
            message=msg.to_dict(),
            sent_at=past_time.isoformat(),
            retry_count=AckSystem.MAX_RETRIES,  # Already at max
            next_retry_at=past_time.isoformat(),
        )

        ack_system._save_pending_acks([ack])

        # Process retries - should escalate
        count = ack_system.process_retries()
        assert count == 1

        # Verify broadcast was called with [UNACKNOWLEDGED]
        mock_broadcast.assert_called_once()
        args = mock_broadcast.call_args[0]
        assert "[UNACKNOWLEDGED]" in args[2]
        assert "agent-2" in args[2]

        # Verify ACK was removed (not retried again)
        pending = ack_system.check_pending_acks()
        assert len(pending) == 0

    def test_process_retries_not_yet_time(self, ack_system: AckSystem) -> None:
        """Test that retries aren't triggered before timeout."""
        now = datetime.now()
        msg = Message(
            sender_id="agent-1",
            timestamp=now,
            msg_type=MessageType.QUESTION,
            content="Test",
            recipients=["agent-2"],
            msg_id="test-msg-id",
        )

        # Add pending ACK with future retry time
        future_time = now + timedelta(seconds=30)
        ack = PendingAck(
            msg_id="test-msg-id",
            sender_id="agent-1",
            recipient_id="agent-2",
            message=msg.to_dict(),
            sent_at=now.isoformat(),
            retry_count=0,
            next_retry_at=future_time.isoformat(),
        )

        ack_system._save_pending_acks([ack])

        # Process retries - nothing should happen
        count = ack_system.process_retries()
        assert count == 0

        # ACK should still be pending
        pending = ack_system.check_pending_acks()
        assert len(pending) == 1

    def test_get_pending_count(self, ack_system: AckSystem) -> None:
        """Test getting pending ACK count."""
        assert ack_system.get_pending_count() == 0

        # Add some ACKs
        now = datetime.now()
        for i in range(3):
            msg = Message(
                sender_id=f"agent-{i}",
                timestamp=now,
                msg_type=MessageType.QUESTION,
                content=f"Test {i}",
                recipients=[f"agent-{i+1}"],
                msg_id=f"msg-{i}",
            )

            ack = PendingAck(
                msg_id=f"msg-{i}",
                sender_id=f"agent-{i}",
                recipient_id=f"agent-{i+1}",
                message=msg.to_dict(),
                sent_at=now.isoformat(),
                retry_count=0,
                next_retry_at=(now + timedelta(seconds=30)).isoformat(),
            )

            ack_system._save_pending_acks(ack_system._load_pending_acks() + [ack])

        assert ack_system.get_pending_count() == 3
        assert ack_system.get_pending_count("agent-1") == 1

    def test_clear_pending_acks(self, ack_system: AckSystem) -> None:
        """Test clearing pending ACKs."""
        now = datetime.now()

        # Add ACKs
        for i in range(3):
            msg = Message(
                sender_id=f"agent-{i}",
                timestamp=now,
                msg_type=MessageType.QUESTION,
                content=f"Test {i}",
                recipients=[f"agent-{i+1}"],
                msg_id=f"msg-{i}",
            )

            ack = PendingAck(
                msg_id=f"msg-{i}",
                sender_id=f"agent-{i}",
                recipient_id=f"agent-{i+1}",
                message=msg.to_dict(),
                sent_at=now.isoformat(),
                retry_count=0,
                next_retry_at=(now + timedelta(seconds=30)).isoformat(),
            )

            ack_system._save_pending_acks(ack_system._load_pending_acks() + [ack])

        # Clear specific agent
        cleared = ack_system.clear_pending_acks("agent-1")
        assert cleared == 1
        assert ack_system.get_pending_count() == 2

        # Clear all
        cleared = ack_system.clear_pending_acks()
        assert cleared == 2
        assert ack_system.get_pending_count() == 0

    def test_thread_safety(self, ack_system: AckSystem) -> None:
        """Test that operations are thread-safe."""
        import threading

        now = datetime.now()
        errors = []

        def add_ack(i: int) -> None:
            try:
                msg = Message(
                    sender_id=f"agent-{i}",
                    timestamp=now,
                    msg_type=MessageType.QUESTION,
                    content=f"Test {i}",
                    recipients=[f"agent-{i+1}"],
                    msg_id=f"msg-{i}",
                )

                ack = PendingAck(
                    msg_id=f"msg-{i}",
                    sender_id=f"agent-{i}",
                    recipient_id=f"agent-{i+1}",
                    message=msg.to_dict(),
                    sent_at=now.isoformat(),
                    retry_count=0,
                    next_retry_at=(now + timedelta(seconds=30)).isoformat(),
                )

                with ack_system._lock:
                    acks = ack_system._load_pending_acks()
                    acks.append(ack)
                    ack_system._save_pending_acks(acks)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=add_ack, args=(i,)) for i in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert ack_system.get_pending_count() == 10


class TestModuleFunctions:
    """Test module-level convenience functions."""

    @pytest.fixture
    def temp_dir(self) -> Path:
        """Create temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @patch("claudeswarm.ack.send_message")
    def test_send_with_ack_function(self, mock_send: MagicMock, temp_dir: Path) -> None:
        """Test module-level send_with_ack function."""
        # Need to reset singleton for testing
        import claudeswarm.ack as ack_module

        ack_module._default_ack_system = AckSystem(temp_dir / "PENDING_ACKS.json")

        now = datetime.now()
        mock_msg = Message(
            sender_id="agent-1",
            timestamp=now,
            msg_type=MessageType.QUESTION,
            content="[REQUIRES-ACK] Test",
            recipients=["agent-2"],
            msg_id="test-id",
        )
        mock_send.return_value = mock_msg

        msg_id = send_with_ack("agent-1", "agent-2", MessageType.QUESTION, "Test")
        assert msg_id == "test-id"

    def test_acknowledge_message_function(self, temp_dir: Path) -> None:
        """Test module-level acknowledge_message function."""
        import claudeswarm.ack as ack_module

        ack_module._default_ack_system = AckSystem(temp_dir / "PENDING_ACKS.json")

        # Add a pending ACK
        now = datetime.now()
        msg = Message(
            sender_id="agent-1",
            timestamp=now,
            msg_type=MessageType.QUESTION,
            content="Test",
            recipients=["agent-2"],
            msg_id="test-id",
        )

        ack = PendingAck(
            msg_id="test-id",
            sender_id="agent-1",
            recipient_id="agent-2",
            message=msg.to_dict(),
            sent_at=now.isoformat(),
            retry_count=0,
            next_retry_at=(now + timedelta(seconds=30)).isoformat(),
        )

        system = get_ack_system()
        system._save_pending_acks([ack])

        # Acknowledge
        result = acknowledge_message("test-id", "agent-2")
        assert result is True

    def test_receive_ack_function(self, temp_dir: Path) -> None:
        """Test module-level receive_ack function (alias)."""
        import claudeswarm.ack as ack_module

        ack_module._default_ack_system = AckSystem(temp_dir / "PENDING_ACKS.json")

        # Add a pending ACK
        now = datetime.now()
        msg = Message(
            sender_id="agent-1",
            timestamp=now,
            msg_type=MessageType.QUESTION,
            content="Test",
            recipients=["agent-2"],
            msg_id="test-id",
        )

        ack = PendingAck(
            msg_id="test-id",
            sender_id="agent-1",
            recipient_id="agent-2",
            message=msg.to_dict(),
            sent_at=now.isoformat(),
            retry_count=0,
            next_retry_at=(now + timedelta(seconds=30)).isoformat(),
        )

        system = get_ack_system()
        system._save_pending_acks([ack])

        # Acknowledge using alias
        result = receive_ack("test-id", "agent-2")
        assert result is True

    def test_check_pending_acks_function(self, temp_dir: Path) -> None:
        """Test module-level check_pending_acks function."""
        import claudeswarm.ack as ack_module

        ack_module._default_ack_system = AckSystem(temp_dir / "PENDING_ACKS.json")

        # Add ACKs
        now = datetime.now()
        system = get_ack_system()

        for i in range(2):
            msg = Message(
                sender_id=f"agent-{i}",
                timestamp=now,
                msg_type=MessageType.QUESTION,
                content=f"Test {i}",
                recipients=[f"agent-{i+1}"],
                msg_id=f"msg-{i}",
            )

            ack = PendingAck(
                msg_id=f"msg-{i}",
                sender_id=f"agent-{i}",
                recipient_id=f"agent-{i+1}",
                message=msg.to_dict(),
                sent_at=now.isoformat(),
                retry_count=0,
                next_retry_at=(now + timedelta(seconds=30)).isoformat(),
            )

            system._save_pending_acks(system._load_pending_acks() + [ack])

        pending = check_pending_acks()
        assert len(pending) == 2

        pending = check_pending_acks("agent-0")
        assert len(pending) == 1


class TestIntegration:
    """Integration tests with messaging system."""

    @pytest.fixture
    def temp_dir(self) -> Path:
        """Create temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def ack_system(self, temp_dir: Path) -> AckSystem:
        """Create AckSystem instance."""
        return AckSystem(temp_dir / "PENDING_ACKS.json")

    @patch("claudeswarm.ack.broadcast_message")
    @patch("claudeswarm.ack.send_message")
    def test_full_workflow_with_ack(
        self, mock_send: MagicMock, mock_broadcast: MagicMock, ack_system: AckSystem
    ) -> None:
        """Test complete workflow: send -> receive ACK."""
        # Mock successful send
        now = datetime.now()
        mock_msg = Message(
            sender_id="agent-1",
            timestamp=now,
            msg_type=MessageType.QUESTION,
            content="[REQUIRES-ACK] Help needed",
            recipients=["agent-2"],
            msg_id="workflow-test",
        )
        mock_send.return_value = mock_msg

        # Send with ACK
        msg_id = ack_system.send_with_ack(
            "agent-1", "agent-2", MessageType.QUESTION, "Help needed"
        )

        assert msg_id == "workflow-test"
        assert ack_system.get_pending_count() == 1

        # Receive ACK
        result = ack_system.receive_ack("workflow-test", "agent-2")
        assert result is True
        assert ack_system.get_pending_count() == 0

    @patch("claudeswarm.ack.broadcast_message")
    @patch("claudeswarm.ack.send_message")
    def test_full_workflow_with_retry_and_escalation(
        self, mock_send: MagicMock, mock_broadcast: MagicMock, ack_system: AckSystem
    ) -> None:
        """Test complete workflow: send -> retry -> retry -> retry -> escalate."""
        now = datetime.now()
        msg = Message(
            sender_id="agent-1",
            timestamp=now,
            msg_type=MessageType.BLOCKED,
            content="[REQUIRES-ACK] Blocked on task",
            recipients=["agent-2"],
            msg_id="escalation-test",
        )

        # Add pending ACK ready for immediate retry
        past = now - timedelta(seconds=1)
        ack = PendingAck(
            msg_id="escalation-test",
            sender_id="agent-1",
            recipient_id="agent-2",
            message=msg.to_dict(),
            sent_at=past.isoformat(),
            retry_count=0,
            next_retry_at=past.isoformat(),
        )

        ack_system._save_pending_acks([ack])

        # First retry
        count = ack_system.process_retries()
        assert count == 1
        assert mock_send.call_count == 1
        assert ack_system.get_pending_count() == 1

        # Update to make ready for second retry
        pending = ack_system.check_pending_acks()[0]
        pending.next_retry_at = past.isoformat()
        ack_system._save_pending_acks([pending])

        # Second retry
        count = ack_system.process_retries()
        assert count == 1
        assert mock_send.call_count == 2
        assert ack_system.get_pending_count() == 1

        # Update to make ready for third retry
        pending = ack_system.check_pending_acks()[0]
        pending.next_retry_at = past.isoformat()
        ack_system._save_pending_acks([pending])

        # Third retry
        count = ack_system.process_retries()
        assert count == 1
        assert mock_send.call_count == 3
        assert ack_system.get_pending_count() == 0  # Removed after max retries

        # Should have escalated
        mock_broadcast.assert_called_once()
        args = mock_broadcast.call_args[0]
        assert "[UNACKNOWLEDGED]" in args[2]
