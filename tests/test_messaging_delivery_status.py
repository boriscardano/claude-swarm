"""
Comprehensive tests for message delivery_status field.

Tests cover:
- Single message success/failure scenarios
- Broadcast partial delivery scenarios
- Tmux unavailable (sandboxed environment)
- JSON serialization of delivery_status
- Message log persistence with delivery_status

Author: Agent-TestCoverage
"""

import json
import subprocess
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call

import pytest

from claudeswarm.messaging import (
    Message,
    MessageType,
    MessageLogger,
    MessagingSystem,
    TmuxMessageDelivery,
    send_message,
    broadcast_message,
    TmuxPaneNotFoundError,
    TmuxSocketError,
)


class TestMessageDeliveryStatus:
    """Tests for delivery_status field in Message class."""

    def test_message_delivery_status_field_exists(self):
        """Test that Message has delivery_status field."""
        msg = Message(
            sender_id="agent-1",
            timestamp=datetime.now(),
            msg_type=MessageType.INFO,
            content="Test",
            recipients=["agent-2"]
        )

        assert hasattr(msg, 'delivery_status')
        assert isinstance(msg.delivery_status, dict)
        assert msg.delivery_status == {}  # Empty by default

    def test_message_to_dict_includes_delivery_status(self):
        """Test that to_dict() includes delivery_status."""
        msg = Message(
            sender_id="agent-1",
            timestamp=datetime.now(),
            msg_type=MessageType.INFO,
            content="Test",
            recipients=["agent-2"]
        )
        msg.delivery_status = {"agent-2": True}

        msg_dict = msg.to_dict()

        assert 'delivery_status' in msg_dict
        assert msg_dict['delivery_status'] == {"agent-2": True}

    def test_message_to_dict_delivery_status_serializable(self):
        """Test that delivery_status can be JSON serialized."""
        msg = Message(
            sender_id="agent-1",
            timestamp=datetime.now(),
            msg_type=MessageType.INFO,
            content="Test",
            recipients=["agent-2", "agent-3"]
        )
        msg.delivery_status = {"agent-2": True, "agent-3": False}

        msg_dict = msg.to_dict()

        # Should be able to serialize to JSON without errors
        json_str = json.dumps(msg_dict)
        parsed = json.loads(json_str)

        assert parsed['delivery_status'] == {"agent-2": True, "agent-3": False}


class TestSingleMessageDeliveryStatus:
    """Tests for delivery_status in single message sending."""

    @patch('claudeswarm.messaging.TmuxMessageDelivery.send_to_pane')
    @patch('claudeswarm.messaging.MessagingSystem._get_agent_pane')
    def test_send_message_success_delivery_status(
        self, mock_get_pane, mock_send_to_pane, tmp_path
    ):
        """Test delivery_status when message is delivered successfully."""
        mock_get_pane.return_value = "test:0.1"
        mock_send_to_pane.return_value = True  # Success

        log_file = tmp_path / "messages.log"
        system = MessagingSystem(log_file=log_file)

        message = system.send_message(
            sender_id="agent-1",
            recipient_id="agent-2",
            msg_type=MessageType.INFO,
            content="Test message"
        )

        assert message is not None
        assert 'agent-2' in message.delivery_status
        assert message.delivery_status['agent-2'] is True

    @patch('claudeswarm.messaging.TmuxMessageDelivery.send_to_pane')
    @patch('claudeswarm.messaging.MessagingSystem._get_agent_pane')
    def test_send_message_failure_delivery_status(
        self, mock_get_pane, mock_send_to_pane, tmp_path
    ):
        """Test delivery_status when tmux delivery fails."""
        mock_get_pane.return_value = "test:0.1"
        mock_send_to_pane.return_value = False  # Failure

        log_file = tmp_path / "messages.log"
        system = MessagingSystem(log_file=log_file)

        message = system.send_message(
            sender_id="agent-1",
            recipient_id="agent-2",
            msg_type=MessageType.INFO,
            content="Test message"
        )

        assert message is not None
        assert 'agent-2' in message.delivery_status
        assert message.delivery_status['agent-2'] is False

    @patch('claudeswarm.messaging.TmuxMessageDelivery.send_to_pane')
    @patch('claudeswarm.messaging.MessagingSystem._get_agent_pane')
    def test_send_message_tmux_exception_delivery_status(
        self, mock_get_pane, mock_send_to_pane, tmp_path
    ):
        """Test delivery_status when tmux raises exception."""
        mock_get_pane.return_value = "test:0.1"
        mock_send_to_pane.side_effect = TmuxSocketError("Tmux socket unavailable")

        log_file = tmp_path / "messages.log"
        system = MessagingSystem(log_file=log_file)

        message = system.send_message(
            sender_id="agent-1",
            recipient_id="agent-2",
            msg_type=MessageType.INFO,
            content="Test message"
        )

        # Message should still be logged even if delivery fails
        assert message is not None
        assert 'agent-2' in message.delivery_status
        assert message.delivery_status['agent-2'] is False


class TestBroadcastDeliveryStatus:
    """Tests for delivery_status in broadcast messages."""

    @patch('claudeswarm.messaging.TmuxMessageDelivery.send_to_pane')
    @patch('claudeswarm.messaging.MessagingSystem._load_agent_registry')
    def test_broadcast_all_success_delivery_status(
        self, mock_load_registry, mock_send_to_pane, tmp_path
    ):
        """Test delivery_status when all broadcasts succeed."""
        # Mock registry with 3 agents
        mock_registry = Mock()
        mock_agent1 = Mock(id="agent-1", pane_index="test:0.0", status="active")
        mock_agent2 = Mock(id="agent-2", pane_index="test:0.1", status="active")
        mock_agent3 = Mock(id="agent-3", pane_index="test:0.2", status="active")
        mock_registry.agents = [mock_agent1, mock_agent2, mock_agent3]
        mock_load_registry.return_value = mock_registry

        mock_send_to_pane.return_value = True  # All succeed

        log_file = tmp_path / "messages.log"
        system = MessagingSystem(log_file=log_file)

        results = system.broadcast_message(
            sender_id="system",
            msg_type=MessageType.INFO,
            content="Broadcast test",
            exclude_self=True
        )

        assert results == {
            "agent-1": True,
            "agent-2": True,
            "agent-3": True
        }

    @patch('claudeswarm.messaging.TmuxMessageDelivery.send_to_pane')
    @patch('claudeswarm.messaging.MessagingSystem._load_agent_registry')
    def test_broadcast_partial_success_delivery_status(
        self, mock_load_registry, mock_send_to_pane, tmp_path
    ):
        """Test delivery_status when some broadcasts succeed and some fail."""
        # Mock registry with 3 agents
        mock_registry = Mock()
        mock_agent1 = Mock(id="agent-1", pane_index="test:0.0", status="active")
        mock_agent2 = Mock(id="agent-2", pane_index="test:0.1", status="active")
        mock_agent3 = Mock(id="agent-3", pane_index="test:0.2", status="active")
        mock_registry.agents = [mock_agent1, mock_agent2, mock_agent3]
        mock_load_registry.return_value = mock_registry

        # First call succeeds, second fails, third succeeds
        mock_send_to_pane.side_effect = [True, False, True]

        log_file = tmp_path / "messages.log"
        system = MessagingSystem(log_file=log_file)

        results = system.broadcast_message(
            sender_id="system",
            msg_type=MessageType.INFO,
            content="Broadcast test",
            exclude_self=True
        )

        assert results == {
            "agent-1": True,
            "agent-2": False,
            "agent-3": True
        }

    @patch('claudeswarm.messaging.TmuxMessageDelivery.send_to_pane')
    @patch('claudeswarm.messaging.MessagingSystem._load_agent_registry')
    def test_broadcast_all_fail_delivery_status(
        self, mock_load_registry, mock_send_to_pane, tmp_path
    ):
        """Test delivery_status when all broadcasts fail."""
        # Mock registry with 2 agents
        mock_registry = Mock()
        mock_agent1 = Mock(id="agent-1", pane_index="test:0.0", status="active")
        mock_agent2 = Mock(id="agent-2", pane_index="test:0.1", status="active")
        mock_registry.agents = [mock_agent1, mock_agent2]
        mock_load_registry.return_value = mock_registry

        mock_send_to_pane.return_value = False  # All fail

        log_file = tmp_path / "messages.log"
        system = MessagingSystem(log_file=log_file)

        results = system.broadcast_message(
            sender_id="system",
            msg_type=MessageType.INFO,
            content="Broadcast test",
            exclude_self=True
        )

        assert results == {
            "agent-1": False,
            "agent-2": False
        }

    @patch('claudeswarm.messaging.TmuxMessageDelivery.send_to_pane')
    @patch('claudeswarm.messaging.MessagingSystem._load_agent_registry')
    def test_broadcast_mixed_exceptions_delivery_status(
        self, mock_load_registry, mock_send_to_pane, tmp_path
    ):
        """Test delivery_status when some broadcasts raise exceptions."""
        # Mock registry with 3 agents
        mock_registry = Mock()
        mock_agent1 = Mock(id="agent-1", pane_index="test:0.0", status="active")
        mock_agent2 = Mock(id="agent-2", pane_index="test:0.1", status="active")
        mock_agent3 = Mock(id="agent-3", pane_index="test:0.2", status="active")
        mock_registry.agents = [mock_agent1, mock_agent2, mock_agent3]
        mock_load_registry.return_value = mock_registry

        # First succeeds, second raises exception, third succeeds
        mock_send_to_pane.side_effect = [
            True,
            TmuxPaneNotFoundError("Pane not found"),
            True
        ]

        log_file = tmp_path / "messages.log"
        system = MessagingSystem(log_file=log_file)

        results = system.broadcast_message(
            sender_id="system",
            msg_type=MessageType.INFO,
            content="Broadcast test",
            exclude_self=True
        )

        assert results == {
            "agent-1": True,
            "agent-2": False,  # Exception treated as failure
            "agent-3": True
        }


class TestDeliveryStatusSandboxedEnvironment:
    """Tests for delivery_status when tmux is unavailable (sandboxed)."""

    @patch('claudeswarm.messaging.TmuxMessageDelivery.send_to_pane')
    @patch('claudeswarm.messaging.MessagingSystem._get_agent_pane')
    def test_sandboxed_send_message_delivery_status(
        self, mock_get_pane, mock_send_to_pane, tmp_path
    ):
        """Test delivery_status when tmux is unavailable (sandboxed environment)."""
        mock_get_pane.return_value = "test:0.1"
        mock_send_to_pane.side_effect = TmuxSocketError("Operation not permitted")

        log_file = tmp_path / "messages.log"
        system = MessagingSystem(log_file=log_file)

        message = system.send_message(
            sender_id="agent-1",
            recipient_id="agent-2",
            msg_type=MessageType.INFO,
            content="Test message"
        )

        # Message logged but delivery failed
        assert message is not None
        assert message.delivery_status['agent-2'] is False

    @patch('claudeswarm.messaging.TmuxMessageDelivery.send_to_pane')
    @patch('claudeswarm.messaging.MessagingSystem._load_agent_registry')
    def test_sandboxed_broadcast_delivery_status(
        self, mock_load_registry, mock_send_to_pane, tmp_path
    ):
        """Test broadcast delivery_status when tmux is unavailable."""
        # Mock registry with 2 agents
        mock_registry = Mock()
        mock_agent1 = Mock(id="agent-1", pane_index="test:0.0", status="active")
        mock_agent2 = Mock(id="agent-2", pane_index="test:0.1", status="active")
        mock_registry.agents = [mock_agent1, mock_agent2]
        mock_load_registry.return_value = mock_registry

        # Tmux unavailable
        mock_send_to_pane.side_effect = TmuxSocketError("Operation not permitted")

        log_file = tmp_path / "messages.log"
        system = MessagingSystem(log_file=log_file)

        results = system.broadcast_message(
            sender_id="system",
            msg_type=MessageType.INFO,
            content="Broadcast test",
            exclude_self=True
        )

        # All deliveries fail but message is logged
        assert results == {
            "agent-1": False,
            "agent-2": False
        }


class TestDeliveryStatusPersistence:
    """Tests for delivery_status persistence in message logs."""

    @patch('claudeswarm.messaging.TmuxMessageDelivery.send_to_pane')
    @patch('claudeswarm.messaging.MessagingSystem._get_agent_pane')
    def test_message_log_includes_delivery_status(
        self, mock_get_pane, mock_send_to_pane, tmp_path
    ):
        """Test that logged messages include delivery_status."""
        mock_get_pane.return_value = "test:0.1"
        mock_send_to_pane.return_value = True

        log_file = tmp_path / "messages.log"
        system = MessagingSystem(log_file=log_file)

        system.send_message(
            sender_id="agent-1",
            recipient_id="agent-2",
            msg_type=MessageType.INFO,
            content="Test message"
        )

        # Read log file
        assert log_file.exists()
        with open(log_file, 'r') as f:
            log_line = f.readline()

        log_entry = json.loads(log_line)

        assert 'delivery_status' in log_entry
        assert log_entry['delivery_status'] == {"agent-2": True}

    @patch('claudeswarm.messaging.TmuxMessageDelivery.send_to_pane')
    @patch('claudeswarm.messaging.MessagingSystem._load_agent_registry')
    def test_broadcast_log_includes_delivery_status(
        self, mock_load_registry, mock_send_to_pane, tmp_path
    ):
        """Test that broadcast logs include delivery_status for all recipients."""
        # Mock registry with 3 agents
        mock_registry = Mock()
        mock_agent1 = Mock(id="agent-1", pane_index="test:0.0", status="active")
        mock_agent2 = Mock(id="agent-2", pane_index="test:0.1", status="active")
        mock_agent3 = Mock(id="agent-3", pane_index="test:0.2", status="active")
        mock_registry.agents = [mock_agent1, mock_agent2, mock_agent3]
        mock_load_registry.return_value = mock_registry

        # Partial success
        mock_send_to_pane.side_effect = [True, False, True]

        log_file = tmp_path / "messages.log"
        system = MessagingSystem(log_file=log_file)

        system.broadcast_message(
            sender_id="system",
            msg_type=MessageType.INFO,
            content="Broadcast test",
            exclude_self=True
        )

        # Read log file
        with open(log_file, 'r') as f:
            log_line = f.readline()

        log_entry = json.loads(log_line)

        assert 'delivery_status' in log_entry
        assert log_entry['delivery_status'] == {
            "agent-1": True,
            "agent-2": False,
            "agent-3": True
        }

    @patch('claudeswarm.messaging.TmuxMessageDelivery.send_to_pane')
    @patch('claudeswarm.messaging.MessagingSystem._get_agent_pane')
    def test_message_log_includes_success_failure_counts(
        self, mock_get_pane, mock_send_to_pane, tmp_path
    ):
        """Test that logged messages include success_count and failure_count."""
        mock_get_pane.return_value = "test:0.1"
        mock_send_to_pane.return_value = True

        log_file = tmp_path / "messages.log"
        system = MessagingSystem(log_file=log_file)

        system.send_message(
            sender_id="agent-1",
            recipient_id="agent-2",
            msg_type=MessageType.INFO,
            content="Test message"
        )

        # Read log file
        with open(log_file, 'r') as f:
            log_line = f.readline()

        log_entry = json.loads(log_line)

        assert 'success_count' in log_entry
        assert 'failure_count' in log_entry
        assert log_entry['success_count'] == 1
        assert log_entry['failure_count'] == 0

    @patch('claudeswarm.messaging.TmuxMessageDelivery.send_to_pane')
    @patch('claudeswarm.messaging.MessagingSystem._load_agent_registry')
    def test_broadcast_log_counts_match_delivery_status(
        self, mock_load_registry, mock_send_to_pane, tmp_path
    ):
        """Test that success/failure counts match delivery_status."""
        # Mock registry with 5 agents
        mock_registry = Mock()
        agents = [
            Mock(id=f"agent-{i}", pane_index=f"test:0.{i}", status="active")
            for i in range(1, 6)
        ]
        mock_registry.agents = agents
        mock_load_registry.return_value = mock_registry

        # 3 succeed, 2 fail
        mock_send_to_pane.side_effect = [True, False, True, False, True]

        log_file = tmp_path / "messages.log"
        system = MessagingSystem(log_file=log_file)

        system.broadcast_message(
            sender_id="system",
            msg_type=MessageType.INFO,
            content="Broadcast test",
            exclude_self=True
        )

        # Read log file
        with open(log_file, 'r') as f:
            log_line = f.readline()

        log_entry = json.loads(log_line)

        assert log_entry['success_count'] == 3
        assert log_entry['failure_count'] == 2
        assert len(log_entry['delivery_status']) == 5


class TestDeliveryStatusPublicAPI:
    """Tests for delivery_status in public API functions."""

    @patch('claudeswarm.messaging.MessagingSystem.send_message')
    def test_send_message_function_returns_delivery_status(self, mock_send):
        """Test that send_message() function returns message with delivery_status."""
        mock_message = Message(
            sender_id="agent-1",
            timestamp=datetime.now(),
            msg_type=MessageType.INFO,
            content="Test",
            recipients=["agent-2"]
        )
        mock_message.delivery_status = {"agent-2": True}
        mock_send.return_value = mock_message

        result = send_message(
            sender_id="agent-1",
            recipient_id="agent-2",
            message_type=MessageType.INFO,
            content="Test"
        )

        assert result is not None
        assert hasattr(result, 'delivery_status')
        assert result.delivery_status == {"agent-2": True}

    @patch('claudeswarm.messaging.MessagingSystem.broadcast_message')
    def test_broadcast_message_function_returns_delivery_status(self, mock_broadcast):
        """Test that broadcast_message() function returns delivery_status dict."""
        mock_broadcast.return_value = {
            "agent-1": True,
            "agent-2": False,
            "agent-3": True
        }

        result = broadcast_message(
            sender_id="system",
            message_type=MessageType.INFO,
            content="Broadcast test"
        )

        assert result == {
            "agent-1": True,
            "agent-2": False,
            "agent-3": True
        }


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
