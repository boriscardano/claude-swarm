"""Inter-agent messaging system for Claude Swarm.

This module provides functionality to:
- Send direct messages to specific agents
- Broadcast messages to all agents
- Format and validate messages
- Integrate with tmux send-keys for message delivery
- Implement rate limiting and logging
- Handle message delivery failures and retries

Messages use a standardized format:
[AGENT-{id}][timestamp][TYPE]: content

Author: Agent-2 (FuchsiaPond)
Phase: Phase 1
"""

from __future__ import annotations

import hmac
import hashlib
import json
import logging
import shlex
import subprocess
import threading
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from .config import get_config
from .discovery import AgentRegistry, get_registry_path
from .utils import get_or_create_secret
from .project import get_messages_log_path
from .file_lock import FileLock, FileLockTimeout, FileLockError
from .validators import (
    ValidationError,
    validate_agent_id,
    validate_message_content,
    validate_rate_limit_config,
    validate_recipient_list,
    sanitize_message_content,
)

__all__ = [
    "MessageType",
    "Message",
    "RateLimiter",
    "TmuxMessageDelivery",
    "MessageLogger",
    "MessagingSystem",
    "send_message",
    "broadcast_message",
    "MessagingError",
    "RateLimitExceeded",
    "AgentNotFoundError",
    "TmuxError",
    "TmuxSocketError",
    "TmuxPaneNotFoundError",
    "TmuxTimeoutError",
    "MessageDeliveryError"
]


# Configure logging
logger = logging.getLogger(__name__)


# Custom exceptions
class MessagingError(Exception):
    """Base exception for messaging system errors."""
    pass


class RateLimitExceeded(MessagingError):
    """Raised when message rate limit is exceeded."""
    pass


class AgentNotFoundError(MessagingError):
    """Raised when target agent cannot be found in registry."""
    pass


class TmuxError(MessagingError):
    """Base exception for tmux-related errors."""
    pass


class TmuxSocketError(TmuxError):
    """Raised when tmux socket is inaccessible or stale."""
    pass


class TmuxPaneNotFoundError(TmuxError):
    """Raised when target tmux pane doesn't exist."""
    pass


class TmuxTimeoutError(TmuxError):
    """Raised when tmux operation times out."""
    pass


class MessageDeliveryError(MessagingError):
    """Raised when message delivery fails."""
    pass


class MessageType(Enum):
    """Types of messages that can be sent between agents."""

    QUESTION = "QUESTION"
    REVIEW_REQUEST = "REVIEW-REQUEST"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    CHALLENGE = "CHALLENGE"
    INFO = "INFO"
    ACK = "ACK"


@dataclass
class Message:
    """Represents a message sent between agents.

    Attributes:
        sender_id: ID of the sending agent
        timestamp: When the message was created
        msg_type: Type of message (from MessageType enum)
        content: Message body/payload
        recipients: List of recipient agent IDs
        msg_id: Unique identifier for tracking (UUID)
        signature: HMAC signature for message authentication (optional, auto-generated)
        delivery_status: Dict mapping recipient_id -> delivery success (populated after sending)
    """

    sender_id: str
    timestamp: datetime
    msg_type: MessageType
    content: str
    recipients: List[str]
    msg_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    signature: str = field(default="")
    delivery_status: Dict[str, bool] = field(default_factory=dict)

    def __post_init__(self):
        """Validate message fields."""
        # Validate sender_id
        try:
            self.sender_id = validate_agent_id(self.sender_id)
        except ValidationError as e:
            raise ValueError(f"Invalid sender_id: {e}")

        # Validate content
        try:
            self.content = validate_message_content(self.content)
        except ValidationError as e:
            raise ValueError(f"Invalid message content: {e}")

        # Validate recipients
        try:
            self.recipients = validate_recipient_list(self.recipients)
        except ValidationError as e:
            raise ValueError(f"Invalid recipients: {e}")

        # Type conversions
        if isinstance(self.msg_type, str):
            self.msg_type = MessageType(self.msg_type)
        if isinstance(self.timestamp, str):
            self.timestamp = datetime.fromisoformat(self.timestamp)

    def _get_message_data_for_signing(self) -> str:
        """Get canonical representation of message for signing.

        Returns:
            String representation of message fields for HMAC signing
        """
        return f"{self.sender_id}|{self.timestamp.isoformat()}|{self.msg_type.value}|{self.content}|{','.join(sorted(self.recipients))}|{self.msg_id}"

    def sign(self, secret: bytes = None) -> None:
        """Sign the message with HMAC-SHA256.

        Args:
            secret: Shared secret for signing (uses default if None)
        """
        if secret is None:
            secret = get_or_create_secret()

        message_data = self._get_message_data_for_signing()
        signature = hmac.new(secret, message_data.encode('utf-8'), hashlib.sha256)
        self.signature = signature.hexdigest()

    def verify_signature(self, secret: bytes = None) -> bool:
        """Verify the message signature.

        Args:
            secret: Shared secret for verification (uses default if None)

        Returns:
            True if signature is valid, False otherwise
        """
        if not self.signature:
            return False

        if secret is None:
            secret = get_or_create_secret()

        message_data = self._get_message_data_for_signing()
        expected_signature = hmac.new(secret, message_data.encode('utf-8'), hashlib.sha256)

        # Use constant-time comparison to prevent timing attacks
        return hmac.compare_digest(self.signature, expected_signature.hexdigest())

    def to_dict(self) -> dict:
        """Convert message to dictionary for serialization.

        This format includes all message fields including signature and is used
        for internal serialization (e.g., ACK system, message reconstruction).
        For log file format, use to_log_dict() instead.
        """
        return {
            'sender_id': self.sender_id,
            'timestamp': self.timestamp.isoformat(),
            'msg_type': self.msg_type.value,
            'content': self.content,
            'recipients': self.recipients,
            'msg_id': self.msg_id,
            'signature': self.signature,
            'delivery_status': self.delivery_status
        }

    def to_log_dict(self) -> dict:
        """Convert message to log file dictionary format.

        This format uses 'sender' instead of 'sender_id' and excludes the signature
        field. It's the format written to agent_messages.log and expected by
        read_messages.py, coord.py, and monitoring.py.
        """
        return {
            'sender': self.sender_id,
            'timestamp': self.timestamp.isoformat(),
            'msg_type': self.msg_type.value,
            'content': self.content,
            'recipients': self.recipients,
            'msg_id': self.msg_id
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Message':
        """Create message from dictionary (internal format with sender_id).

        This expects the format from to_dict() which includes 'sender_id' and
        'signature' fields. For parsing log file entries, use from_log_dict() instead.
        """
        return cls(
            sender_id=data['sender_id'],
            timestamp=datetime.fromisoformat(data['timestamp']),
            msg_type=MessageType(data['msg_type']),
            content=data['content'],
            recipients=data['recipients'],
            msg_id=data.get('msg_id', str(uuid.uuid4())),
            signature=data.get('signature', '')
        )

    @classmethod
    def from_log_dict(cls, data: dict) -> 'Message':
        """Create message from log file dictionary format.

        This expects the format from agent_messages.log which uses 'sender'
        instead of 'sender_id' and may not have a 'signature' field.
        Extra fields like 'delivery_status', 'success_count', and 'failure_count'
        are ignored.
        """
        return cls(
            sender_id=data['sender'],  # Note: log format uses 'sender'
            timestamp=datetime.fromisoformat(data['timestamp']),
            msg_type=MessageType(data['msg_type']),
            content=data['content'],
            recipients=data['recipients'],
            msg_id=data.get('msg_id', str(uuid.uuid4())),
            signature=''  # Log format doesn't include signature
        )

    def format_for_display(self) -> str:
        """Format message for terminal display.

        Format: [AGENT-ID][TIMESTAMP][TYPE]: content
        Example: [agent-0][2025-11-07 14:30:15][QUESTION]: What database schema?
        """
        timestamp_str = self.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        return f"[{self.sender_id}][{timestamp_str}][{self.msg_type.value}]: {self.content}"


class RateLimiter:
    """Rate limiter for message sending.

    Enforces maximum number of messages per agent per time window.
    Defaults are configurable via .claudeswarm.yaml/toml configuration file.
    """

    def __init__(self, max_messages: Optional[int] = None, window_seconds: Optional[int] = None):
        """Initialize rate limiter.

        Args:
            max_messages: Maximum messages allowed per window (None = use config default)
            window_seconds: Time window in seconds (None = use config default)

        Raises:
            ValidationError: If rate limit configuration is invalid
        """
        # Use config defaults if not explicitly provided
        if max_messages is None or window_seconds is None:
            config = get_config()
            if max_messages is None:
                max_messages = config.rate_limiting.messages_per_minute
            if window_seconds is None:
                window_seconds = config.rate_limiting.window_seconds

        # Validate rate limit configuration
        try:
            self.max_messages, self.window_seconds = validate_rate_limit_config(
                max_messages, window_seconds
            )
        except ValidationError as e:
            raise ValueError(f"Invalid rate limit configuration: {e}")

        # Track message timestamps per agent
        self._message_times: Dict[str, deque] = defaultdict(lambda: deque(maxlen=self.max_messages))

        # Thread safety lock for protecting shared state
        self._lock = threading.Lock()

    def check_rate_limit(self, agent_id: str) -> bool:
        """Check if agent is within rate limit.

        Args:
            agent_id: ID of the agent to check

        Returns:
            True if within limit, False if rate limit exceeded
        """
        with self._lock:
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
        with self._lock:
            self._message_times[agent_id].append(datetime.now())

    def reset_agent(self, agent_id: str):
        """Reset rate limit for a specific agent."""
        with self._lock:
            if agent_id in self._message_times:
                del self._message_times[agent_id]

    def cleanup_inactive_agents(self, cutoff_seconds: int = 3600):
        """Remove tracking data for agents that haven't sent messages recently.

        This prevents memory leaks in long-running scenarios where agents
        come and go but their tracking data remains in memory.

        Args:
            cutoff_seconds: Remove agents inactive for this many seconds (default: 1 hour)

        Returns:
            Number of agents cleaned up
        """
        with self._lock:
            now = datetime.now()
            cutoff = now - timedelta(seconds=cutoff_seconds)

            # Find agents with no recent activity
            agents_to_remove = []
            for agent_id, times in self._message_times.items():
                if not times or (times and times[-1] < cutoff):
                    agents_to_remove.append(agent_id)

            # Remove inactive agents
            for agent_id in agents_to_remove:
                del self._message_times[agent_id]

            return len(agents_to_remove)


class TmuxMessageDelivery:
    """Handles message delivery via tmux send-keys.

    Provides proper escaping and error handling for tmux integration.
    """

    @staticmethod
    def escape_for_tmux(text: str) -> str:
        """Escape text for safe transmission via tmux send-keys.

        Uses shlex.quote() for proper shell escaping to prevent command injection.

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
        # Use shlex.quote for safe shell escaping
        # This prevents command injection by properly quoting the text
        return shlex.quote(text)

    @staticmethod
    def send_to_pane(pane_id: str, message: str, timeout: float = 10.0) -> bool:
        """Send message to a specific tmux pane.

        Args:
            pane_id: tmux pane identifier (e.g., "session:0.1")
            message: Message text to send
            timeout: Timeout in seconds for tmux operations (default: 10.0)

        Returns:
            True if successful

        Raises:
            TmuxPaneNotFoundError: If pane doesn't exist
            TmuxSocketError: If tmux socket is inaccessible
            TmuxTimeoutError: If operation times out
            TmuxError: For other tmux errors
        """
        try:
            # First verify pane exists to give better error messages
            if not TmuxMessageDelivery.verify_pane_exists(pane_id):
                raise TmuxPaneNotFoundError(
                    f"Tmux pane {pane_id} not found. It may have been closed or the agent terminated."
                )

            # Escape the message
            escaped = TmuxMessageDelivery.escape_for_tmux(message)

            # Use bash comment to display message (no execution, no approval needed)
            cmd = f"# [MESSAGE] {escaped}"

            # Send command text to tmux pane
            result = subprocess.run(
                ['tmux', 'send-keys', '-t', pane_id, cmd],
                capture_output=True,
                text=True,
                timeout=timeout
            )

            if result.returncode != 0:
                stderr = result.stderr.lower() if result.stderr else ""
                if "no server running" in stderr:
                    raise TmuxSocketError("Tmux server is not running")
                elif "can't find pane" in stderr or "pane not found" in stderr:
                    raise TmuxPaneNotFoundError(f"Pane {pane_id} not found")
                elif "operation not permitted" in stderr or "permission denied" in stderr:
                    raise TmuxSocketError(
                        f"Permission denied accessing tmux socket. "
                        f"The socket may have wrong permissions or be stale. Error: {result.stderr}"
                    )
                else:
                    raise TmuxError(f"Failed to send command to pane {pane_id}: {result.stderr}")

            # Send Enter key separately to execute the command
            result = subprocess.run(
                ['tmux', 'send-keys', '-t', pane_id, 'Enter'],
                capture_output=True,
                text=True,
                timeout=timeout
            )

            if result.returncode != 0:
                stderr = result.stderr.lower() if result.stderr else ""
                if "can't find pane" in stderr or "pane not found" in stderr:
                    raise TmuxPaneNotFoundError(f"Pane {pane_id} not found")
                else:
                    raise TmuxError(f"Failed to send Enter to pane {pane_id}: {result.stderr}")

            logger.debug(f"Successfully sent message to pane {pane_id}")
            return True

        except subprocess.TimeoutExpired as e:
            raise TmuxTimeoutError(
                f"Timeout ({timeout}s) sending to pane {pane_id}. "
                f"The message may be too large or tmux may be unresponsive."
            ) from e
        except FileNotFoundError as e:
            raise TmuxError("tmux command not found. Is tmux installed?") from e
        except (TmuxError, TmuxSocketError, TmuxPaneNotFoundError, TmuxTimeoutError):
            # Re-raise our custom exceptions
            raise
        except Exception as e:
            raise TmuxError(f"Unexpected error sending to pane {pane_id}: {e}") from e

    @staticmethod
    def verify_pane_exists(pane_id: str, timeout: float = 5.0) -> bool:
        """Verify that a tmux pane exists.

        Args:
            pane_id: tmux pane identifier
            timeout: Timeout in seconds for tmux operation

        Returns:
            True if pane exists, False otherwise

        Note:
            Returns False for any errors (socket issues, timeouts, etc.)
            to avoid raising exceptions during validation checks.
        """
        try:
            result = subprocess.run(
                ['tmux', 'list-panes', '-a', '-F', '#{session_name}:#{window_index}.#{pane_index}'],
                capture_output=True,
                text=True,
                timeout=timeout
            )

            if result.returncode != 0:
                stderr = result.stderr.lower() if result.stderr else ""
                if "no server running" in stderr:
                    logger.debug("Tmux server not running")
                elif "operation not permitted" in stderr or "permission denied" in stderr:
                    logger.warning(f"Permission denied accessing tmux socket: {result.stderr}")
                return False

            # Check if our pane_id is in the list
            panes = result.stdout.strip().split('\n')
            exists = pane_id in panes or any(pane_id in p for p in panes)
            logger.debug(f"Pane {pane_id} exists: {exists}")
            return exists

        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout verifying pane {pane_id}")
            return False
        except FileNotFoundError:
            logger.warning("tmux command not found")
            return False
        except Exception as e:
            logger.error(f"Error verifying pane {pane_id}: {e}")
            return False


class MessageLogger:
    """Handles structured logging of messages to JSON log file.

    Features:
    - JSON format for easy parsing
    - Log rotation when file exceeds 10MB
    - Thread-safe writing
    """

    def __init__(self, log_file: Optional[Path] = None, project_root: Optional[Path] = None):
        """Initialize message logger.

        Args:
            log_file: Path to log file (default: project_root/agent_messages.log)
            project_root: Optional project root directory
        """
        self.log_file = log_file or get_messages_log_path(project_root)
        self.max_size = 10 * 1024 * 1024  # 10MB

        # Create log file if it doesn't exist
        if not self.log_file.exists():
            self.log_file.touch()

    def log_message(self, message: Message, delivery_status: Dict[str, bool]):
        """Log a message with delivery status.

        Writes entries to agent_messages.log in a standardized JSON format.
        Each line is a separate JSON object with the following fields:
        - sender: agent ID (string)
        - timestamp: ISO format timestamp (string)
        - msg_type: message type enum value (string)
        - content: message content (string)
        - recipients: list of recipient agent IDs (list)
        - msg_id: unique message identifier (string)
        - delivery_status: dict of recipient -> success (dict)
        - success_count: number of successful deliveries (int)
        - failure_count: number of failed deliveries (int)

        Note: Uses 'sender' field (not 'sender_id') to maintain backward
        compatibility with existing parsing code.

        Uses exclusive file lock to prevent concurrent writes from corrupting
        the log file when multiple agents write simultaneously.

        Args:
            message: Message that was sent
            delivery_status: Dict mapping recipient_id -> success/failure
        """
        # Start with base message fields in log format
        log_entry = message.to_log_dict()

        # Add delivery-specific fields
        log_entry['delivery_status'] = delivery_status
        log_entry['success_count'] = sum(1 for success in delivery_status.values() if success)
        log_entry['failure_count'] = sum(1 for success in delivery_status.values() if not success)

        # Update timestamp to current time (log time, not message creation time)
        log_entry['timestamp'] = datetime.now().isoformat()

        # Use exclusive lock to protect both rotation check and write
        # This prevents multiple agents from interleaving JSON lines
        try:
            with FileLock(self.log_file, timeout=2.0, shared=False):
                # Check if we need to rotate
                self._rotate_if_needed()

                # Append to log file
                with open(self.log_file, 'a') as f:
                    f.write(json.dumps(log_entry) + '\n')

        except FileLockTimeout:
            # Log warning but don't crash - graceful degradation
            logger.warning(
                f"Timeout acquiring lock on {self.log_file} for message {message.msg_id}. "
                f"Message logging skipped to avoid blocking."
            )
        except (FileLockError, OSError, IOError) as e:
            # Handle other file locking or I/O errors gracefully
            logger.error(
                f"Failed to log message {message.msg_id} to {self.log_file}: {e}"
            )

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


class MessagingSystem:
    """Main messaging system for Claude Swarm.

    Coordinates all messaging operations including:
    - Direct messaging
    - Broadcasting
    - Rate limiting
    - Message logging

    Configuration values default to .claudeswarm.yaml/toml settings.
    """

    def __init__(
        self,
        log_file: Path = None,
        rate_limit_messages: Optional[int] = None,
        rate_limit_window: Optional[int] = None
    ):
        """Initialize messaging system.

        Args:
            log_file: Path to message log file
            rate_limit_messages: Max messages per agent per window (None = use config)
            rate_limit_window: Rate limit window in seconds (None = use config)
        """
        self.rate_limiter = RateLimiter(rate_limit_messages, rate_limit_window)
        self.message_logger = MessageLogger(log_file)
        self.delivery = TmuxMessageDelivery()

    def _load_agent_registry(self) -> Optional[AgentRegistry]:
        """Load the current agent registry with file locking.

        Uses shared (read) lock to prevent race conditions when
        multiple processes access the registry simultaneously.

        Returns:
            AgentRegistry if found, None otherwise

        Raises:
            FileLockTimeout: If cannot acquire lock within timeout
        """
        registry_path = get_registry_path()
        if not registry_path.exists():
            logger.debug(f"Agent registry not found at {registry_path}")
            return None

        try:
            # Use shared lock for reading (allows multiple readers)
            with FileLock(registry_path, timeout=5.0, shared=True):
                with open(registry_path, 'r') as f:
                    data = json.load(f)
                return AgentRegistry.from_dict(data)

        except FileLockTimeout as e:
            logger.error(f"Timeout acquiring lock on registry: {e}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in agent registry {registry_path}: {e}")
            return None
        except KeyError as e:
            logger.error(f"Missing required field in registry: {e}")
            return None
        except Exception as e:
            logger.error(f"Error loading agent registry: {e}")
            return None

    def _get_agent_pane(self, agent_id: str) -> Optional[str]:
        """Get tmux pane ID for an agent.

        Args:
            agent_id: ID of the agent

        Returns:
            Pane ID if found

        Raises:
            AgentNotFoundError: If agent not found or not active
            FileLockTimeout: If cannot acquire registry lock
        """
        registry = self._load_agent_registry()
        if not registry:
            raise AgentNotFoundError(
                f"Agent registry not found. No agents are currently registered. "
                f"Run 'claudeswarm refresh' to update the registry."
            )

        # Look for the agent
        for agent in registry.agents:
            if agent.id == agent_id:
                if agent.status == "active":
                    return agent.pane_index
                else:
                    raise AgentNotFoundError(
                        f"Agent {agent_id} found but has status '{agent.status}' (not active). "
                        f"The agent may have terminated or become stale."
                    )

        # Agent not in registry at all
        available_agents = [a.id for a in registry.agents if a.status == "active"]
        if available_agents:
            raise AgentNotFoundError(
                f"Agent {agent_id} not found in registry. "
                f"Available active agents: {', '.join(available_agents)}"
            )
        else:
            raise AgentNotFoundError(
                f"Agent {agent_id} not found and no active agents are available. "
                f"Run 'claudeswarm refresh' to update the registry."
            )

    def send_message(
        self,
        sender_id: str,
        recipient_id: str,
        msg_type: MessageType,
        content: str
    ) -> Message:
        """Send a direct message to a specific agent.

        Args:
            sender_id: ID of sending agent
            recipient_id: ID of receiving agent
            msg_type: Type of message
            content: Message content

        Returns:
            Message object if successful

        Raises:
            RateLimitExceeded: If sender has exceeded rate limit
            AgentNotFoundError: If recipient agent not found or not active
            TmuxError: If tmux operation fails (socket, pane, timeout)
            MessageDeliveryError: If message delivery fails for other reasons
        """
        # Check rate limit first
        if not self.rate_limiter.check_rate_limit(sender_id):
            max_messages = self.rate_limiter.max_messages
            window_seconds = self.rate_limiter.window_seconds
            raise RateLimitExceeded(
                f"Rate limit exceeded for {sender_id}. "
                f"Maximum {max_messages} messages per {window_seconds} seconds. "
                f"Please wait before sending more messages."
            )

        # Validate recipient exists before creating message
        # This raises AgentNotFoundError with detailed message if not found
        pane_id = self._get_agent_pane(recipient_id)

        # Create message
        try:
            message = Message(
                sender_id=sender_id,
                timestamp=datetime.now(),
                msg_type=msg_type,
                content=content,
                recipients=[recipient_id]
            )
        except ValueError as e:
            raise MessageDeliveryError(f"Invalid message data: {e}") from e

        # Sign the message for authentication
        message.sign()

        # Format and send message
        formatted_msg = message.format_for_display()

        # Track delivery success for logging
        success = False
        error_msg = None
        tmux_unavailable = False

        try:
            self.delivery.send_to_pane(pane_id, formatted_msg)
            success = True
            logger.info(f"Message {message.msg_id} delivered to {recipient_id}")

        except (TmuxError, TmuxSocketError, TmuxPaneNotFoundError, TmuxTimeoutError) as e:
            # Tmux errors are expected in sandboxed environments
            # Don't raise - just log to file and continue
            error_msg = str(e)
            tmux_unavailable = True
            logger.debug(f"Tmux delivery unavailable for message {message.msg_id} to {recipient_id}: {e}")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Unexpected error delivering message {message.msg_id} to {recipient_id}: {e}")
            raise MessageDeliveryError(f"Message delivery failed: {e}") from e

        finally:
            # Always record rate limit if we got past the rate limit check
            # (even if delivery failed, we attempted to send)
            self.rate_limiter.record_message(sender_id)

            # Always log the message attempt (inbox delivery)
            delivery_status = {recipient_id: success}

            # Store delivery status in message for CLI access
            message.delivery_status = delivery_status

            try:
                self.message_logger.log_message(message, delivery_status)
            except Exception as log_error:
                logger.warning(f"Failed to log message: {log_error}")

        return message

    def broadcast_message(
        self,
        sender_id: str,
        msg_type: MessageType,
        content: str,
        exclude_self: bool = True,
        max_recipients: int = 100
    ) -> Dict[str, bool]:
        """Broadcast a message to all active agents.

        Args:
            sender_id: ID of sending agent
            msg_type: Type of message
            content: Message content
            exclude_self: Whether to exclude sender from broadcast
            max_recipients: Maximum number of recipients (safety limit)

        Returns:
            Dict mapping recipient_id -> success/failure

        Raises:
            RateLimitExceeded: If sender has exceeded rate limit
            AgentNotFoundError: If no active recipients found
            MessageDeliveryError: If broadcast validation fails
            FileLockTimeout: If cannot acquire registry lock
        """
        # Check rate limit first
        if not self.rate_limiter.check_rate_limit(sender_id):
            max_messages = self.rate_limiter.max_messages
            window_seconds = self.rate_limiter.window_seconds
            raise RateLimitExceeded(
                f"Rate limit exceeded for {sender_id}. "
                f"Maximum {max_messages} messages per {window_seconds} seconds. "
                f"Please wait before sending more messages."
            )

        # Load agent registry with file locking
        registry = self._load_agent_registry()
        if not registry:
            raise AgentNotFoundError(
                "Agent registry not found. No agents are currently registered. "
                "Run 'claudeswarm refresh' to update the registry."
            )

        # Get all active recipients
        recipients = []
        for agent in registry.agents:
            if agent.status != "active":
                continue
            if exclude_self and agent.id == sender_id:
                continue
            recipients.append(agent.id)

        # Validate recipients
        if not recipients:
            if exclude_self:
                available = [a.id for a in registry.agents if a.status == "active"]
                if sender_id in available and len(available) == 1:
                    raise AgentNotFoundError(
                        f"No other active agents found for broadcast (only {sender_id} is active). "
                        "Cannot broadcast to self when exclude_self=True."
                    )
            raise AgentNotFoundError(
                "No active recipients found for broadcast. "
                "Run 'claudeswarm refresh' to update the registry."
            )

        # Validate recipient count
        if len(recipients) > max_recipients:
            raise MessageDeliveryError(
                f"Too many recipients ({len(recipients)}) for broadcast. "
                f"Maximum is {max_recipients}. Consider using targeted messages instead."
            )

        logger.info(f"Broadcasting to {len(recipients)} recipients: {', '.join(recipients)}")

        # Create message
        try:
            message = Message(
                sender_id=sender_id,
                timestamp=datetime.now(),
                msg_type=msg_type,
                content=content,
                recipients=recipients
            )
        except ValueError as e:
            raise MessageDeliveryError(f"Invalid broadcast message data: {e}") from e

        # Sign the message for authentication
        message.sign()

        # Format message once for efficiency
        formatted_msg = message.format_for_display()

        # Send to all recipients, tracking successes and failures
        delivery_status = {}
        for recipient_id in recipients:
            try:
                # Get pane without raising (handle gracefully for broadcast)
                pane_id = None
                for agent in registry.agents:
                    if agent.id == recipient_id and agent.status == "active":
                        pane_id = agent.pane_index
                        break

                if not pane_id:
                    logger.warning(f"Pane not found for recipient {recipient_id}")
                    delivery_status[recipient_id] = False
                    continue

                # Attempt delivery with shorter timeout for broadcasts
                self.delivery.send_to_pane(pane_id, formatted_msg, timeout=5.0)
                delivery_status[recipient_id] = True
                logger.debug(f"Broadcast delivered to {recipient_id}")

            except (TmuxPaneNotFoundError, TmuxSocketError) as e:
                logger.warning(f"Failed to deliver broadcast to {recipient_id}: {e}")
                delivery_status[recipient_id] = False

            except TmuxTimeoutError as e:
                logger.warning(f"Timeout delivering broadcast to {recipient_id}: {e}")
                delivery_status[recipient_id] = False

            except Exception as e:
                logger.error(f"Unexpected error delivering broadcast to {recipient_id}: {e}")
                delivery_status[recipient_id] = False

        # Always record rate limit (we attempted the broadcast)
        self.rate_limiter.record_message(sender_id)

        # Store delivery status in message for CLI access
        message.delivery_status = delivery_status

        # Log the message
        try:
            self.message_logger.log_message(message, delivery_status)
        except Exception as log_error:
            logger.warning(f"Failed to log broadcast message: {log_error}")

        # Log summary
        success_count = sum(1 for s in delivery_status.values() if s)
        failure_count = sum(1 for s in delivery_status.values() if not s)
        total_count = len(delivery_status)

        if success_count == 0:
            logger.error(
                f"Broadcast {message.msg_id} from {sender_id} completely failed: "
                f"0/{total_count} delivered. All recipients unreachable."
            )
        elif failure_count > 0:
            logger.warning(
                f"Broadcast {message.msg_id} from {sender_id} partially successful: "
                f"{success_count}/{total_count} delivered, {failure_count} failed"
            )
        else:
            logger.info(
                f"Broadcast {message.msg_id} from {sender_id}: "
                f"{success_count}/{total_count} delivered successfully"
            )

        return delivery_status


# Module-level convenience functions

_default_messaging_system = None

def _get_messaging_system() -> MessagingSystem:
    """Get or create the default messaging system instance."""
    global _default_messaging_system
    if _default_messaging_system is None:
        _default_messaging_system = MessagingSystem()
    return _default_messaging_system


def send_message(
    sender_id: str,
    recipient_id: str,
    message_type: MessageType,
    content: str
) -> Optional[Message]:
    """Send a direct message to a specific agent.

    This is a convenience wrapper around MessagingSystem.send_message()
    that maintains backward compatibility by returning None on error
    instead of raising exceptions.

    For better error handling, use MessagingSystem directly.

    Args:
        sender_id: ID of sending agent
        recipient_id: ID of receiving agent
        message_type: Type of message to send
        content: Message content

    Returns:
        Message object if successful, None if failed

    Note:
        This function catches all exceptions and returns None for
        backward compatibility. Check logs for error details.
    """
    try:
        messaging = _get_messaging_system()
        return messaging.send_message(sender_id, recipient_id, message_type, content)
    except (RateLimitExceeded, AgentNotFoundError, TmuxError, MessageDeliveryError) as e:
        logger.error(f"send_message failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in send_message: {e}")
        return None


def broadcast_message(
    sender_id: str,
    message_type: MessageType,
    content: str,
    exclude_self: bool = True
) -> Dict[str, bool]:
    """Broadcast a message to all active agents.

    This is a convenience wrapper around MessagingSystem.broadcast_message()
    that maintains backward compatibility by returning empty dict on error
    instead of raising exceptions.

    For better error handling, use MessagingSystem directly.

    Args:
        sender_id: ID of sending agent
        message_type: Type of message to send
        content: Message content
        exclude_self: If True, don't send to current agent

    Returns:
        Dictionary mapping agent IDs to delivery success status,
        or empty dict if broadcast failed

    Note:
        This function catches all exceptions and returns {} for
        backward compatibility. Check logs for error details.
    """
    try:
        messaging = _get_messaging_system()
        return messaging.broadcast_message(sender_id, message_type, content, exclude_self)
    except (RateLimitExceeded, AgentNotFoundError, MessageDeliveryError) as e:
        logger.error(f"broadcast_message failed: {e}")
        return {}
    except Exception as e:
        logger.error(f"Unexpected error in broadcast_message: {e}")
        return {}
