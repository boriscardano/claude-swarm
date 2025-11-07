"""
Claude Swarm - Messaging System

This module implements the messaging system for Claude Swarm, enabling
reliable communication between Claude Code agents via tmux send-keys.

Features:
- Message formatting and validation
- Direct messaging (point-to-point)
- Broadcast messaging
- tmux send-keys integration with proper escaping
- Message logging (structured JSON)
- Rate limiting (10 messages/agent/minute)

Author: Agent-2 (FuchsiaPond)
Phase: Phase 1
"""

import json
import logging
import re
import subprocess
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import List, Dict, Optional, Set
from collections import defaultdict, deque


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MessageType(Enum):
    """Message types for agent communication."""
    QUESTION = "QUESTION"
    REVIEW_REQUEST = "REVIEW-REQUEST"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    CHALLENGE = "CHALLENGE"
    INFO = "INFO"
    ACK = "ACK"


@dataclass
class Message:
    """
    Message structure for agent communication.

    Attributes:
        sender_id: ID of the sending agent (e.g., "agent-0", "FuchsiaPond")
        timestamp: When the message was created
        msg_type: Type of message (from MessageType enum)
        content: Message content/body
        recipients: List of recipient agent IDs
        msg_id: Unique message identifier (UUID)
    """
    sender_id: str
    timestamp: datetime
    msg_type: MessageType
    content: str
    recipients: List[str]
    msg_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self):
        """Validate message fields."""
        if not self.sender_id:
            raise ValueError("sender_id cannot be empty")
        if not self.content:
            raise ValueError("content cannot be empty")
        if not self.recipients:
            raise ValueError("recipients cannot be empty")
        if isinstance(self.msg_type, str):
            self.msg_type = MessageType(self.msg_type)
        if isinstance(self.timestamp, str):
            self.timestamp = datetime.fromisoformat(self.timestamp)

    def to_dict(self) -> dict:
        """Convert message to dictionary for serialization."""
        return {
            'sender_id': self.sender_id,
            'timestamp': self.timestamp.isoformat(),
            'msg_type': self.msg_type.value,
            'content': self.content,
            'recipients': self.recipients,
            'msg_id': self.msg_id
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Message':
        """Create message from dictionary."""
        return cls(
            sender_id=data['sender_id'],
            timestamp=datetime.fromisoformat(data['timestamp']),
            msg_type=MessageType(data['msg_type']),
            content=data['content'],
            recipients=data['recipients'],
            msg_id=data.get('msg_id', str(uuid.uuid4()))
        )

    def format_for_display(self) -> str:
        """
        Format message for terminal display.

        Format: [AGENT-ID][TIMESTAMP][TYPE]: content
        Example: [agent-0][2025-11-07 14:30:15][QUESTION]: What database schema?
        """
        timestamp_str = self.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        return f"[{self.sender_id}][{timestamp_str}][{self.msg_type.value}]: {self.content}"


class RateLimiter:
    """
    Rate limiter for message sending.

    Enforces maximum of 10 messages per agent per minute.
    """

    def __init__(self, max_messages: int = 10, window_seconds: int = 60):
        """
        Initialize rate limiter.

        Args:
            max_messages: Maximum messages allowed per window
            window_seconds: Time window in seconds
        """
        self.max_messages = max_messages
        self.window_seconds = window_seconds
        # Track message timestamps per agent
        self._message_times: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_messages))

    def check_rate_limit(self, agent_id: str) -> bool:
        """
        Check if agent is within rate limit.

        Args:
            agent_id: ID of the agent to check

        Returns:
            True if within limit, False if rate limit exceeded
        """
        now = datetime.now()
        cutoff = now - timedelta(seconds=self.window_seconds)

        # Remove old timestamps
        times = self._message_times[agent_id]
        while times and times[0] < cutoff:
            times.popleft()

        # Check if we're at the limit
        if len(times) >= self.max_messages:
            return False

        return True

    def record_message(self, agent_id: str):
        """Record that a message was sent by an agent."""
        self._message_times[agent_id].append(datetime.now())

    def reset_agent(self, agent_id: str):
        """Reset rate limit for a specific agent."""
        if agent_id in self._message_times:
            del self._message_times[agent_id]


class TmuxMessageDelivery:
    """
    Handles message delivery via tmux send-keys.

    Provides proper escaping and error handling for tmux integration.
    """

    @staticmethod
    def escape_for_tmux(text: str) -> str:
        """
        Escape text for safe transmission via tmux send-keys.

        Handles:
        - Single quotes
        - Double quotes
        - Newlines
        - Special shell characters

        Args:
            text: Text to escape

        Returns:
            Escaped text safe for tmux send-keys
        """
        # Replace single quotes with '\''
        text = text.replace("'", "'\"'\"'")
        # Replace newlines with literal \n for echo
        text = text.replace("\n", "\\n")
        return text

    @staticmethod
    def send_to_pane(pane_id: str, message: str) -> bool:
        """
        Send message to a specific tmux pane.

        Args:
            pane_id: tmux pane identifier (e.g., "session:0.1")
            message: Message text to send

        Returns:
            True if successful, False otherwise
        """
        try:
            # Escape the message
            escaped = TmuxMessageDelivery.escape_for_tmux(message)

            # Use echo to display the message (with -e to interpret \n)
            cmd = f"echo -e '{escaped}'"

            # Send to tmux pane
            result = subprocess.run(
                ['tmux', 'send-keys', '-t', pane_id, cmd, 'Enter'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode != 0:
                logger.error(f"Failed to send to pane {pane_id}: {result.stderr}")
                return False

            return True

        except subprocess.TimeoutExpired:
            logger.error(f"Timeout sending to pane {pane_id}")
            return False
        except Exception as e:
            logger.error(f"Error sending to pane {pane_id}: {e}")
            return False

    @staticmethod
    def verify_pane_exists(pane_id: str) -> bool:
        """
        Verify that a tmux pane exists.

        Args:
            pane_id: tmux pane identifier

        Returns:
            True if pane exists, False otherwise
        """
        try:
            result = subprocess.run(
                ['tmux', 'list-panes', '-a', '-F', '#{pane_id}'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode != 0:
                return False

            # Check if our pane_id is in the list
            panes = result.stdout.strip().split('\n')
            return pane_id in panes or any(pane_id in p for p in panes)

        except Exception as e:
            logger.error(f"Error verifying pane {pane_id}: {e}")
            return False


class MessageLogger:
    """
    Handles structured logging of messages to JSON log file.

    Features:
    - JSON format for easy parsing
    - Log rotation when file exceeds 10MB
    - Thread-safe writing
    """

    def __init__(self, log_file: Path = None):
        """
        Initialize message logger.

        Args:
            log_file: Path to log file (default: ./agent_messages.log)
        """
        self.log_file = log_file or Path("./agent_messages.log")
        self.max_size = 10 * 1024 * 1024  # 10MB

        # Create log file if it doesn't exist
        if not self.log_file.exists():
            self.log_file.touch()

    def log_message(self, message: Message, delivery_status: Dict[str, bool]):
        """
        Log a message with delivery status.

        Args:
            message: Message that was sent
            delivery_status: Dict mapping recipient_id -> success/failure
        """
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'msg_id': message.msg_id,
            'sender': message.sender_id,
            'recipients': message.recipients,
            'msg_type': message.msg_type.value,
            'content': message.content,
            'delivery_status': delivery_status,
            'success_count': sum(1 for success in delivery_status.values() if success),
            'failure_count': sum(1 for success in delivery_status.values() if not success)
        }

        # Check if we need to rotate
        self._rotate_if_needed()

        # Append to log file
        with open(self.log_file, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')

    def _rotate_if_needed(self):
        """Rotate log file if it exceeds max size."""
        if not self.log_file.exists():
            return

        if self.log_file.stat().st_size > self.max_size:
            # Rename to .old
            old_log = self.log_file.with_suffix('.log.old')
            if old_log.exists():
                old_log.unlink()
            self.log_file.rename(old_log)
            self.log_file.touch()
            logger.info(f"Rotated log file to {old_log}")


# TODO: This will be replaced with actual AgentRegistry from Agent-1
@dataclass
class MockAgent:
    """Mock agent structure - will be replaced by Agent-1's implementation."""
    id: str
    pane_index: str
    pid: int
    status: str
    last_seen: datetime
    session_name: str


class MessagingSystem:
    """
    Main messaging system for Claude Swarm.

    Coordinates all messaging operations including:
    - Direct messaging
    - Broadcasting
    - Rate limiting
    - Message logging
    """

    def __init__(
        self,
        log_file: Path = None,
        rate_limit_messages: int = 10,
        rate_limit_window: int = 60
    ):
        """
        Initialize messaging system.

        Args:
            log_file: Path to message log file
            rate_limit_messages: Max messages per agent per window
            rate_limit_window: Rate limit window in seconds
        """
        self.rate_limiter = RateLimiter(rate_limit_messages, rate_limit_window)
        self.message_logger = MessageLogger(log_file)
        self.delivery = TmuxMessageDelivery()

        # TODO: This will be replaced with actual registry integration
        self._agent_registry: Dict[str, MockAgent] = {}

    def register_mock_agent(self, agent: MockAgent):
        """
        Temporary method to register mock agents for testing.
        Will be replaced by integration with Agent-1's discovery system.
        """
        self._agent_registry[agent.id] = agent

    def _get_agent_pane(self, agent_id: str) -> Optional[str]:
        """
        Get tmux pane ID for an agent.

        TODO: This will use Agent-1's AgentRegistry

        Args:
            agent_id: ID of the agent

        Returns:
            Pane ID if found, None otherwise
        """
        agent = self._agent_registry.get(agent_id)
        if not agent:
            logger.error(f"Agent {agent_id} not found in registry")
            return None

        return agent.pane_index

    def send_message(
        self,
        sender_id: str,
        recipient_id: str,
        msg_type: MessageType,
        content: str
    ) -> Optional[Message]:
        """
        Send a direct message to a specific agent.

        Args:
            sender_id: ID of sending agent
            recipient_id: ID of receiving agent
            msg_type: Type of message
            content: Message content

        Returns:
            Message object if successful, None if failed
        """
        # Check rate limit
        if not self.rate_limiter.check_rate_limit(sender_id):
            logger.warning(f"Rate limit exceeded for {sender_id}")
            return None

        # Create message
        message = Message(
            sender_id=sender_id,
            timestamp=datetime.now(),
            msg_type=msg_type,
            content=content,
            recipients=[recipient_id]
        )

        # Get recipient pane
        pane_id = self._get_agent_pane(recipient_id)
        if not pane_id:
            logger.error(f"Cannot find pane for agent {recipient_id}")
            return None

        # Format and send message
        formatted_msg = message.format_for_display()
        success = self.delivery.send_to_pane(pane_id, formatted_msg)

        # Record rate limit
        if success:
            self.rate_limiter.record_message(sender_id)

        # Log the message
        delivery_status = {recipient_id: success}
        self.message_logger.log_message(message, delivery_status)

        if success:
            logger.info(f"Message {message.msg_id} delivered to {recipient_id}")
        else:
            logger.error(f"Failed to deliver message {message.msg_id} to {recipient_id}")

        return message if success else None

    def broadcast_message(
        self,
        sender_id: str,
        msg_type: MessageType,
        content: str,
        exclude_self: bool = True
    ) -> Dict[str, bool]:
        """
        Broadcast a message to all agents.

        Args:
            sender_id: ID of sending agent
            msg_type: Type of message
            content: Message content
            exclude_self: Whether to exclude sender from broadcast

        Returns:
            Dict mapping recipient_id -> success/failure
        """
        # Check rate limit
        if not self.rate_limiter.check_rate_limit(sender_id):
            logger.warning(f"Rate limit exceeded for {sender_id}")
            return {}

        # Get all recipients
        recipients = []
        for agent_id in self._agent_registry.keys():
            if exclude_self and agent_id == sender_id:
                continue
            recipients.append(agent_id)

        if not recipients:
            logger.warning(f"No recipients found for broadcast from {sender_id}")
            return {}

        # Create message
        message = Message(
            sender_id=sender_id,
            timestamp=datetime.now(),
            msg_type=msg_type,
            content=content,
            recipients=recipients
        )

        # Format message once
        formatted_msg = message.format_for_display()

        # Send to all recipients
        delivery_status = {}
        for recipient_id in recipients:
            pane_id = self._get_agent_pane(recipient_id)
            if not pane_id:
                delivery_status[recipient_id] = False
                continue

            success = self.delivery.send_to_pane(pane_id, formatted_msg)
            delivery_status[recipient_id] = success

        # Record rate limit
        self.rate_limiter.record_message(sender_id)

        # Log the message
        self.message_logger.log_message(message, delivery_status)

        # Log results
        success_count = sum(1 for s in delivery_status.values() if s)
        total_count = len(delivery_status)
        logger.info(
            f"Broadcast {message.msg_id} from {sender_id}: "
            f"{success_count}/{total_count} delivered successfully"
        )

        return delivery_status


# CLI helper functions (to be integrated into cli.py later)

def cli_send_to_agent(target: str, msg_type: str, content: str, sender: str = "cli"):
    """
    CLI command to send message to a specific agent.

    Usage: send-to-agent <target> <type> <message>
    """
    messaging = MessagingSystem()

    try:
        message_type = MessageType[msg_type.upper().replace('-', '_')]
    except KeyError:
        print(f"Error: Invalid message type '{msg_type}'")
        print(f"Valid types: {', '.join(t.value for t in MessageType)}")
        return 1

    result = messaging.send_message(sender, target, message_type, content)

    if result:
        print(f"Message sent successfully (ID: {result.msg_id})")
        return 0
    else:
        print("Failed to send message")
        return 1


def cli_broadcast_to_all(msg_type: str, content: str, sender: str = "cli"):
    """
    CLI command to broadcast message to all agents.

    Usage: broadcast-to-all <type> <message>
    """
    messaging = MessagingSystem()

    try:
        message_type = MessageType[msg_type.upper().replace('-', '_')]
    except KeyError:
        print(f"Error: Invalid message type '{msg_type}'")
        print(f"Valid types: {', '.join(t.value for t in MessageType)}")
        return 1

    results = messaging.broadcast_message(sender, message_type, content)

    if results:
        success_count = sum(1 for s in results.values() if s)
        total_count = len(results)
        print(f"Broadcast sent: {success_count}/{total_count} delivered successfully")

        # Show failures
        failures = [agent for agent, success in results.items() if not success]
        if failures:
            print(f"Failed deliveries: {', '.join(failures)}")

        return 0 if success_count > 0 else 1
    else:
        print("Failed to send broadcast")
        return 1


if __name__ == "__main__":
    # Basic test
    print("Claude Swarm Messaging System")
    print("=" * 50)
    print(f"MessageType enum values: {[t.value for t in MessageType]}")

    # Test message creation
    msg = Message(
        sender_id="test-agent",
        timestamp=datetime.now(),
        msg_type=MessageType.INFO,
        content="Test message",
        recipients=["agent-1"]
    )
    print(f"\nSample message: {msg.format_for_display()}")
    print(f"Message ID: {msg.msg_id}")

    # Test serialization
    msg_dict = msg.to_dict()
    print(f"\nSerialized: {json.dumps(msg_dict, indent=2)}")

    # Test deserialization
    msg2 = Message.from_dict(msg_dict)
    print(f"Deserialized: {msg2.format_for_display()}")

    # Test escaping
    test_text = "This has 'quotes' and \"double quotes\" and\nnewlines"
    escaped = TmuxMessageDelivery.escape_for_tmux(test_text)
    print(f"\nOriginal: {test_text}")
    print(f"Escaped: {escaped}")
