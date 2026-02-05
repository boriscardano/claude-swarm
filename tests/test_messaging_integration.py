"""
Integration tests for messaging system with discovery.

These tests verify that messaging integrates correctly with the discovery system.
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from claudeswarm.messaging import MessageType, MessagingSystem, TmuxMessageDelivery


class TestMessagingDiscoveryIntegration:
    """Tests for messaging system integration with discovery."""

    @patch("claudeswarm.messaging.get_registry_path")
    def test_load_agent_registry(self, mock_get_path):
        """Test that messaging system can load agent registry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a mock registry file
            registry_path = Path(tmpdir) / "ACTIVE_AGENTS.json"
            registry_data = {
                "session_name": "test-session",
                "updated_at": datetime.now().isoformat(),
                "agents": [
                    {
                        "id": "agent-1",
                        "pane_index": "session:0.1",
                        "pid": 12345,
                        "status": "active",
                        "last_seen": datetime.now().isoformat(),
                        "session_name": "test-session",
                    },
                    {
                        "id": "agent-2",
                        "pane_index": "session:0.2",
                        "pid": 12346,
                        "status": "active",
                        "last_seen": datetime.now().isoformat(),
                        "session_name": "test-session",
                    },
                ],
            }
            with open(registry_path, "w") as f:
                json.dump(registry_data, f)

            mock_get_path.return_value = registry_path

            system = MessagingSystem()
            registry = system._load_agent_registry()

            assert registry is not None
            assert len(registry.agents) == 2
            assert registry.agents[0].id == "agent-1"
            assert registry.agents[1].id == "agent-2"

    @patch("claudeswarm.messaging.get_registry_path")
    def test_get_agent_pane(self, mock_get_path):
        """Test getting agent pane from registry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "ACTIVE_AGENTS.json"
            registry_data = {
                "session_name": "test-session",
                "updated_at": datetime.now().isoformat(),
                "agents": [
                    {
                        "id": "agent-1",
                        "pane_index": "session:0.1",
                        "pid": 12345,
                        "status": "active",
                        "last_seen": datetime.now().isoformat(),
                        "session_name": "test-session",
                    }
                ],
            }
            with open(registry_path, "w") as f:
                json.dump(registry_data, f)

            mock_get_path.return_value = registry_path

            system = MessagingSystem()
            pane = system._get_agent_pane("agent-1")

            assert pane == "session:0.1"

    @patch("claudeswarm.messaging.get_registry_path")
    @patch.object(TmuxMessageDelivery, "send_to_pane")
    def test_send_message_with_registry(self, mock_send, mock_get_path):
        """Test sending message using discovery registry."""
        mock_send.return_value = True

        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "ACTIVE_AGENTS.json"
            log_file = Path(tmpdir) / "messages.log"

            registry_data = {
                "session_name": "test-session",
                "updated_at": datetime.now().isoformat(),
                "agents": [
                    {
                        "id": "agent-1",
                        "pane_index": "session:0.1",
                        "pid": 12345,
                        "status": "active",
                        "last_seen": datetime.now().isoformat(),
                        "session_name": "test-session",
                    },
                    {
                        "id": "agent-2",
                        "pane_index": "session:0.2",
                        "pid": 12346,
                        "status": "active",
                        "last_seen": datetime.now().isoformat(),
                        "session_name": "test-session",
                    },
                ],
            }
            with open(registry_path, "w") as f:
                json.dump(registry_data, f)

            mock_get_path.return_value = registry_path

            system = MessagingSystem(log_file=log_file)
            result = system.send_message("agent-1", "agent-2", MessageType.INFO, "Test message")

            assert result is not None
            assert result.sender_id == "agent-1"
            assert result.recipients == ["agent-2"]
            mock_send.assert_called_once()

    @patch("claudeswarm.messaging.get_registry_path")
    @patch.object(TmuxMessageDelivery, "send_to_pane")
    def test_broadcast_with_registry(self, mock_send, mock_get_path):
        """Test broadcasting message using discovery registry."""
        mock_send.return_value = True

        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "ACTIVE_AGENTS.json"
            log_file = Path(tmpdir) / "messages.log"

            # Create registry with 4 agents
            agents = [
                {
                    "id": f"agent-{i}",
                    "pane_index": f"session:0.{i}",
                    "pid": 12345 + i,
                    "status": "active",
                    "last_seen": datetime.now().isoformat(),
                    "session_name": "test-session",
                }
                for i in range(4)
            ]

            registry_data = {
                "session_name": "test-session",
                "updated_at": datetime.now().isoformat(),
                "agents": agents,
            }
            with open(registry_path, "w") as f:
                json.dump(registry_data, f)

            mock_get_path.return_value = registry_path

            system = MessagingSystem(log_file=log_file)
            results = system.broadcast_message(
                "agent-0", MessageType.INFO, "Broadcast test", exclude_self=True
            )

            # Should send to 3 agents (excluding agent-0)
            assert len(results) == 3
            assert "agent-0" not in results
            assert all(results.values())
            assert mock_send.call_count == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
