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

import hashlib
import hmac
import json
import shlex
import subprocess
import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path

from .config import get_config
from .discovery import AgentRegistry, get_registry_path
from .file_lock import FileLock, FileLockError, FileLockTimeout
from .logging_config import get_logger
from .project import get_messages_log_path
from .utils import get_or_create_secret
from .validators import (
    ValidationError,
    validate_agent_id,
    validate_message_content,
    validate_rate_limit_config,
    validate_recipient_list,
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
    "MessageDeliveryError",
]


# ============================================================================
# MESSAGING SYSTEM CONSTANTS
# ============================================================================

# Timeout for direct message delivery via tmux (seconds)
# Generous timeout to handle slow systems and ensure reliable delivery
DIRECT_MESSAGE_TIMEOUT_SECONDS = 10.0

# Timeout for broadcast message delivery via tmux (seconds)
# Shorter than direct messages to prevent one slow agent from blocking entire broadcast
BROADCAST_TIMEOUT_SECONDS = 5.0

# Timeout for tmux pane verification (seconds)
TMUX_VERIFY_TIMEOUT_SECONDS = 5.0

# Maximum message log file size before rotation (bytes)
# 10MB provides good balance between file size and history retention
MESSAGE_LOG_MAX_SIZE_BYTES = 10 * 1024 * 1024

# File lock timeout for message log writes (seconds)
# Short timeout since log writes are fast (<1ms typically)
MESSAGE_LOG_LOCK_TIMEOUT_SECONDS = 2.0

# File lock timeout for registry reads (seconds)
REGISTRY_READ_LOCK_TIMEOUT_SECONDS = 5.0

# Maximum number of recipients for broadcast (safety limit)
# Prevents accidental DOS from broadcasting to huge agent lists
MAX_BROADCAST_RECIPIENTS = 100

# Retry configuration for tmux operations
# Handles transient failures (socket issues, timeouts) with exponential backoff
MAX_TMUX_RETRIES = 3
TMUX_INITIAL_RETRY_DELAY = 0.1
TMUX_MAX_RETRY_DELAY = 1.0
TMUX_JITTER_FACTOR = 0.25

# Cleanup interval for inactive agent rate limiters (seconds)
# Remove rate limit tracking for agents inactive for 1 hour
RATE_LIMITER_CLEANUP_SECONDS = 3600

# Configure logging
logger = get_logger(__name__)


def _calculate_tmux_backoff(attempt: int) -> float:
    """Calculate retry delay with exponential backoff and jitter.

    Uses exponential backoff (0.1s, 0.2s, 0.4s...) capped at 1s,
    with random jitter (±25%) to prevent thundering herd.

    Args:
        attempt: Zero-based attempt number (0 = first retry)

    Returns:
        Delay in seconds before next retry attempt
    """
    import random

    base_delay = TMUX_INITIAL_RETRY_DELAY * (2**attempt)
    base_delay = min(base_delay, TMUX_MAX_RETRY_DELAY)
    jitter = base_delay * TMUX_JITTER_FACTOR * (2 * random.random() - 1)
    return max(0.01, base_delay + jitter)


def _is_transient_tmux_error(error_msg: str) -> bool:
    """Check if error is transient and worth retrying.

    Transient errors are temporary conditions that may resolve on retry:
    - Server not responding (tmux server busy/overloaded)
    - Connection refused (socket temporarily unavailable)
    - Resource temporarily unavailable (system under load)
    - Timed out (operation took too long)

    Args:
        error_msg: Error message string to analyze

    Returns:
        True if error appears transient and retry may succeed
    """
    transient_patterns = [
        "server not responding",
        "connection refused",
        "resource temporarily unavailable",
        "timed out",
    ]
    error_lower = error_msg.lower()
    return any(p in error_lower for p in transient_patterns)


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
    recipients: list[str]
    msg_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    signature: str = field(default="")
    delivery_status: dict[str, bool] = field(default_factory=dict)

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
        signature = hmac.new(secret, message_data.encode("utf-8"), hashlib.sha256)
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
        expected_signature = hmac.new(secret, message_data.encode("utf-8"), hashlib.sha256)

        # Use constant-time comparison to prevent timing attacks
        return hmac.compare_digest(self.signature, expected_signature.hexdigest())

    def to_dict(self) -> dict:
        """Convert message to dictionary for serialization.

        This format includes all message fields including signature and is used
        for internal serialization (e.g., ACK system, message reconstruction).
        For log file format, use to_log_dict() instead.
        """
        return {
            "sender_id": self.sender_id,
            "timestamp": self.timestamp.isoformat(),
            "msg_type": self.msg_type.value,
            "content": self.content,
            "recipients": self.recipients,
            "msg_id": self.msg_id,
            "signature": self.signature,
            "delivery_status": self.delivery_status,
        }

    def to_log_dict(self) -> dict:
        """Convert message to log file dictionary format.

        This format uses 'sender' instead of 'sender_id' and excludes the signature
        field. It's the format written to agent_messages.log and expected by
        read_messages.py, coord.py, and monitoring.py.
        """
        return {
            "sender": self.sender_id,
            "timestamp": self.timestamp.isoformat(),
            "msg_type": self.msg_type.value,
            "content": self.content,
            "recipients": self.recipients,
            "msg_id": self.msg_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Message:
        """Create message from dictionary (internal format with sender_id).

        This expects the format from to_dict() which includes 'sender_id' and
        'signature' fields. For parsing log file entries, use from_log_dict() instead.
        """
        return cls(
            sender_id=data["sender_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            msg_type=MessageType(data["msg_type"]),
            content=data["content"],
            recipients=data["recipients"],
            msg_id=data.get("msg_id", str(uuid.uuid4())),
            signature=data.get("signature", ""),
        )

    @classmethod
    def from_log_dict(cls, data: dict) -> Message:
        """Create message from log file dictionary format.

        This expects the format from agent_messages.log which uses 'sender'
        instead of 'sender_id' and may not have a 'signature' field.
        Extra fields like 'delivery_status', 'success_count', and 'failure_count'
        are ignored.
        """
        return cls(
            sender_id=data["sender"],  # Note: log format uses 'sender'
            timestamp=datetime.fromisoformat(data["timestamp"]),
            msg_type=MessageType(data["msg_type"]),
            content=data["content"],
            recipients=data["recipients"],
            msg_id=data.get("msg_id", str(uuid.uuid4())),
            signature="",  # Log format doesn't include signature
        )

    def format_for_display(self) -> str:
        """Format message for terminal display.

        Format: [AGENT-ID][TIMESTAMP][TYPE]: content
        Example: [agent-0][2025-11-07 14:30:15][QUESTION]: What database schema?
        """
        timestamp_str = self.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        return f"[{self.sender_id}][{timestamp_str}][{self.msg_type.value}]: {self.content}"


class RateLimiter:
    """Rate limiter for message sending.

    Enforces maximum number of messages per agent per time window.
    Defaults are configurable via .claudeswarm.yaml/toml configuration file.
    """

    def __init__(self, max_messages: int | None = None, window_seconds: int | None = None):
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
        self._message_times: dict[str, deque] = defaultdict(lambda: deque(maxlen=self.max_messages))

        # Thread safety lock for protecting shared state
        self._lock = threading.Lock()

        # Counter for periodic cleanup (prevent memory leaks)
        self._cleanup_counter = 0

    def check_rate_limit(self, agent_id: str) -> bool:
        """Check if agent is within rate limit.

        Args:
            agent_id: ID of the agent to check

        Returns:
            True if within limit, False if rate limit exceeded
        """
        with self._lock:
            # Periodic cleanup to prevent memory leaks (every 100 checks)
            self._cleanup_counter += 1
            if self._cleanup_counter >= 100:
                self._cleanup_counter = 0
                # Use 5-minute inactivity threshold for cleanup
                self._cleanup_inactive_agents_internal(cutoff_seconds=300)

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

    def check_rate_limit_bulk(self, agent_id: str, count: int) -> bool:
        """Check if agent can send multiple messages within rate limit.

        This method is used for broadcasts to ensure that sending a message
        to N recipients counts as N messages toward the rate limit, preventing
        broadcast DoS attacks where an agent could send 10 broadcasts to 100
        recipients each (1000 effective messages) while appearing to stay
        within a 10 msg/min limit.

        Args:
            agent_id: ID of the agent to check
            count: Number of messages to check (e.g., number of broadcast recipients)

        Returns:
            True if sending count messages would be within limit, False otherwise
        """
        with self._lock:
            now = datetime.now()
            cutoff = now - timedelta(seconds=self.window_seconds)

            # Remove old timestamps
            times = self._message_times[agent_id]
            while times and times[0] < cutoff:
                times.popleft()

            # Check if we have room for count more messages
            if len(times) + count > self.max_messages:
                return False

            return True

    def record_message(self, agent_id: str, count: int = 1):
        """Record that message(s) were sent by an agent.

        Args:
            agent_id: ID of the agent
            count: Number of messages to record (default: 1)
        """
        with self._lock:
            now = datetime.now()
            # Record count timestamps for rate limiting
            for _ in range(count):
                self._message_times[agent_id].append(now)

    def reset_agent(self, agent_id: str):
        """Reset rate limit for a specific agent."""
        with self._lock:
            if agent_id in self._message_times:
                del self._message_times[agent_id]

    def _cleanup_inactive_agents_internal(self, cutoff_seconds: int = 300):
        """Internal cleanup method called automatically during check_rate_limit.

        This is called periodically (every 100 rate limit checks) to prevent
        memory leaks from inactive agents. Uses a shorter 5-minute threshold
        by default for more aggressive cleanup.

        Args:
            cutoff_seconds: Remove agents inactive for this many seconds (default: 5 minutes)

        Note:
            This method assumes the caller already holds self._lock.
            For external cleanup, use cleanup_inactive_agents() instead.
        """
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

        if agents_to_remove:
            logger.debug(f"Cleaned up {len(agents_to_remove)} inactive agents from rate limiter")

    def cleanup_inactive_agents(self, cutoff_seconds: int = RATE_LIMITER_CLEANUP_SECONDS):
        """Remove tracking data for agents that haven't sent messages recently.

        This prevents memory leaks in long-running scenarios where agents
        come and go but their tracking data remains in memory.

        This is the public API for manual cleanup. For automatic periodic cleanup,
        see _cleanup_inactive_agents_internal() which is called automatically.

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
    def send_to_pane(
        pane_id: str, message: str, timeout: float = DIRECT_MESSAGE_TIMEOUT_SECONDS
    ) -> bool:
        """Send message to a specific tmux pane with retry on transient failures.

        Wraps _send_to_pane_once with automatic retry logic for transient errors
        (timeouts, socket errors). Permanent failures (pane not found) are not retried.

        Args:
            pane_id: tmux pane identifier (e.g., "session:0.1" or "%N")
            message: Message text to send
            timeout: Timeout in seconds for tmux operations (default: 10.0)

        Returns:
            True if successful

        Raises:
            TmuxPaneNotFoundError: If pane doesn't exist (not retried)
            TmuxSocketError: If tmux socket is inaccessible after all retries
            TmuxTimeoutError: If operation times out after all retries
            TmuxError: For other tmux errors
        """
        last_exception: Exception | None = None

        for attempt in range(MAX_TMUX_RETRIES + 1):
            try:
                return TmuxMessageDelivery._send_to_pane_once(pane_id, message, timeout)
            except TmuxPaneNotFoundError:
                # Permanent failure - pane doesn't exist, don't retry
                raise
            except (TmuxTimeoutError, TmuxSocketError) as e:
                last_exception = e
                if attempt < MAX_TMUX_RETRIES:
                    delay = _calculate_tmux_backoff(attempt)
                    logger.info(
                        f"Tmux error, retrying ({attempt + 1}/{MAX_TMUX_RETRIES}) "
                        f"after {delay:.2f}s: {e}"
                    )
                    time.sleep(delay)
            except TmuxError as e:
                # Check if this is a transient error worth retrying
                if _is_transient_tmux_error(str(e)) and attempt < MAX_TMUX_RETRIES:
                    last_exception = e
                    delay = _calculate_tmux_backoff(attempt)
                    logger.info(
                        f"Transient error, retrying ({attempt + 1}/{MAX_TMUX_RETRIES}): {e}"
                    )
                    time.sleep(delay)
                else:
                    raise

        # All retries exhausted
        if last_exception:
            raise last_exception
        # This shouldn't happen, but satisfy type checker
        raise TmuxError("Send failed after all retries")

    @staticmethod
    def _send_to_pane_once(
        pane_id: str, message: str, timeout: float = DIRECT_MESSAGE_TIMEOUT_SECONDS
    ) -> bool:
        """Send message to a specific tmux pane (single attempt, no retry).

        Internal method that performs one delivery attempt. Use send_to_pane()
        for automatic retry handling.

        Args:
            pane_id: tmux pane identifier (e.g., "session:0.1" or "%N")
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
            # Validate pane ID format to prevent command injection
            # Pane IDs should not contain shell metacharacters
            if not isinstance(pane_id, str) or not pane_id:
                raise TmuxError("Invalid pane ID: must be a non-empty string")

            # Check for shell metacharacters that could cause injection
            # Tmux accepts multiple formats: session:window.pane or %number
            # We just need to ensure no shell metacharacters
            dangerous_chars = set(";&|`$(){}[]<>*?!")
            if any(c in pane_id for c in dangerous_chars):
                raise TmuxError(f"Invalid pane ID '{pane_id}': contains shell metacharacters")

            # First verify pane exists to give better error messages
            if not TmuxMessageDelivery.verify_pane_exists(pane_id):
                raise TmuxPaneNotFoundError(
                    f"Tmux pane {pane_id} not found. It may have been closed or the agent terminated."
                )

            # Format message for display (no escaping needed with -l flag)
            cmd = f"# [MESSAGE] {message}"

            # Send command text to tmux pane using -l for literal interpretation
            # The -l flag treats the text literally, preventing command injection
            result = subprocess.run(
                ["tmux", "send-keys", "-l", "-t", pane_id, cmd],
                capture_output=True,
                text=True,
                timeout=timeout,
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
            # Add small delay to ensure message text is processed before Enter
            time.sleep(0.1)

            result = subprocess.run(
                ["tmux", "send-keys", "-t", pane_id, "Enter"],
                capture_output=True,
                text=True,
                timeout=timeout,
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
    def verify_pane_exists(pane_id: str, timeout: float = TMUX_VERIFY_TIMEOUT_SECONDS) -> bool:
        """Verify that a tmux pane exists.

        Supports both pane ID formats:
        - session:window.pane format (e.g., "0:1.0")
        - %N format (e.g., "%5") - stable internal pane ID

        Args:
            pane_id: tmux pane identifier in either format
            timeout: Timeout in seconds for tmux operation

        Returns:
            True if pane exists, False otherwise

        Note:
            Returns False for any errors (socket issues, timeouts, etc.)
            to avoid raising exceptions during validation checks.
        """
        try:
            # Use different format string based on pane_id format
            if pane_id.startswith("%"):
                # Use pane_id format (%N) for matching - more stable
                format_str = "#{pane_id}"
            else:
                # Use session:window.pane format for matching
                format_str = "#{session_name}:#{window_index}.#{pane_index}"

            result = subprocess.run(
                ["tmux", "list-panes", "-a", "-F", format_str],
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            if result.returncode != 0:
                stderr = result.stderr.lower() if result.stderr else ""
                if "no server running" in stderr:
                    logger.debug("Tmux server not running")
                elif "operation not permitted" in stderr or "permission denied" in stderr:
                    logger.warning(f"Permission denied accessing tmux socket: {result.stderr}")
                return False

            # Check if our pane_id is in the list
            panes = result.stdout.strip().split("\n")
            exists = pane_id in panes
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

    def __init__(self, log_file: Path | None = None, project_root: Path | None = None):
        """Initialize message logger.

        Args:
            log_file: Path to log file (default: project_root/agent_messages.log)
            project_root: Optional project root directory
        """
        self.log_file = log_file or get_messages_log_path(project_root)
        self.max_size = MESSAGE_LOG_MAX_SIZE_BYTES

        # Create log file if it doesn't exist
        if not self.log_file.exists():
            self.log_file.touch()

    def log_message(self, message: Message, delivery_status: dict[str, bool]):
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
        log_entry["delivery_status"] = delivery_status
        log_entry["success_count"] = sum(1 for success in delivery_status.values() if success)
        log_entry["failure_count"] = sum(1 for success in delivery_status.values() if not success)

        # Update timestamp to current time (log time, not message creation time)
        log_entry["timestamp"] = datetime.now().isoformat()

        # Use exclusive lock to protect both rotation check and write
        # This prevents multiple agents from interleaving JSON lines
        try:
            with FileLock(self.log_file, timeout=MESSAGE_LOG_LOCK_TIMEOUT_SECONDS, shared=False):
                # Check if we need to rotate
                self._rotate_if_needed()

                # Append to log file
                with open(self.log_file, "a") as f:
                    f.write(json.dumps(log_entry) + "\n")

        except FileLockTimeout:
            # Log warning but don't crash - graceful degradation
            logger.warning(
                f"Timeout acquiring lock on {self.log_file} for message {message.msg_id}. "
                f"Message logging skipped to avoid blocking."
            )
        except (FileLockError, OSError) as e:
            # Handle other file locking or I/O errors gracefully
            logger.error(f"Failed to log message {message.msg_id} to {self.log_file}: {e}")

    def _rotate_if_needed(self):
        """Rotate log file if it exceeds max size."""
        if not self.log_file.exists():
            return

        if self.log_file.stat().st_size > self.max_size:
            # Rename to .old
            old_log = self.log_file.with_suffix(".log.old")
            if old_log.exists():
                old_log.unlink()
            self.log_file.rename(old_log)
            self.log_file.touch()
            logger.info(f"Rotated log file to {old_log}")

    def get_messages_for_agent(self, agent_id: str, limit: int | None = None) -> list[dict]:
        """Get messages for a specific agent from the log file.

        Reads messages from agent_messages.log and filters for messages
        sent to the specified agent. Returns the most recent messages
        up to the limit.

        Args:
            agent_id: ID of the agent to get messages for
            limit: Maximum number of messages to return (most recent first)

        Returns:
            List of message dictionaries, ordered by timestamp (most recent last)

        Note:
            Returns empty list if log file doesn't exist or no messages found.
            Silently skips invalid JSON lines in the log file.
        """
        if not self.log_file.exists():
            return []

        messages = []
        try:
            with open(self.log_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        msg = json.loads(line)

                        # Check if this message is for the specified agent
                        recipients = msg.get("recipients", [])
                        if agent_id in recipients or "all" in recipients:
                            messages.append(msg)
                    except json.JSONDecodeError as e:
                        # Log corrupted JSON entries for debugging
                        logger.warning(
                            f"Skipping corrupted JSON entry in {self.log_file}: {e}. "
                            f"Line content (truncated): {line[:100]}"
                        )
                        continue

        except OSError as e:
            logger.warning(f"Error reading messages from {self.log_file}: {e}")
            return []

        # Return the most recent messages up to limit
        if limit and limit > 0:
            return messages[-limit:]
        return messages


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
        rate_limit_messages: int | None = None,
        rate_limit_window: int | None = None,
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

    def _load_agent_registry(self) -> AgentRegistry | None:
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
            with FileLock(registry_path, timeout=REGISTRY_READ_LOCK_TIMEOUT_SECONDS, shared=True):
                with open(registry_path) as f:
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

    def _get_agent_pane(self, agent_id: str) -> str | None:
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
                "Agent registry not found. No agents are currently registered. "
                "Run 'claudeswarm refresh' to update the registry."
            )

        # Look for the agent
        for agent in registry.agents:
            if agent.id == agent_id:
                if agent.status == "active":
                    # Prefer stable tmux_pane_id (%N format) if available
                    # Falls back to pane_index for backward compatibility
                    if agent.tmux_pane_id:
                        return agent.tmux_pane_id
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
        self, sender_id: str, recipient_id: str, msg_type: MessageType, content: str
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
                recipients=[recipient_id],
            )
        except ValueError as e:
            raise MessageDeliveryError(f"Invalid message data: {e}") from e

        # Sign the message for authentication
        message.sign()

        # Format and send message
        formatted_msg = message.format_for_display()

        # ========================================================================
        # MESSAGE DELIVERY WITH GRACEFUL FALLBACK STRATEGY
        # ========================================================================
        # This implements a dual-delivery system that ensures messages are logged
        # even when real-time tmux delivery fails. This is critical for supporting
        # both interactive (tmux-available) and sandboxed (tmux-unavailable)
        # environments.
        #
        # WHY DUAL DELIVERY:
        # Messages have two delivery channels:
        # 1. Real-time tmux delivery (immediate notification in recipient's terminal)
        # 2. File-based inbox (persistent message log in agent_messages.log)
        #
        # Both channels serve different purposes:
        # - Tmux: Immediate, interactive notifications
        # - Log file: Persistent inbox, supports asynchronous reading, survives restarts
        #
        # GRACEFUL DEGRADATION STRATEGY:
        #
        # Claude Code runs in three types of environments:
        #
        # A) Full tmux environment (normal operation):
        # - Tmux socket is accessible
        # - Real-time delivery succeeds
        # - Message also logged to file for persistence
        # - Recipient sees message immediately in terminal
        #
        # B) Sandboxed environment (Claude Code in browser/API):
        # - Tmux socket is not accessible or permission denied
        # - Real-time delivery fails with TmuxError
        # - Message is STILL logged to file (fallback)
        # - Recipient can read from log file asynchronously
        # - This allows messaging to work even without tmux
        #
        # C) Partial failure (agent terminated):
        # - Tmux pane no longer exists (agent closed)
        # - Real-time delivery fails with TmuxPaneNotFoundError
        # - Message is still logged for potential recovery
        # - Rate limit is still consumed (we attempted delivery)
        #
        # EXCEPTION HANDLING HIERARCHY:
        #
        # 1. TmuxError/TmuxSocketError/TmuxPaneNotFoundError/TmuxTimeoutError:
        # These are EXPECTED in sandboxed environments. We:
        # - Log at DEBUG level (not ERROR - this is normal)
        # - Mark tmux_unavailable = True (for metrics)
        # - DO NOT raise exception (fallback to file-based delivery)
        # - Continue to log message to file
        # - Return message object normally
        #
        # 2. Exception (catch-all):
        # Unexpected errors that indicate bugs or system issues:
        # - Log at ERROR level
        # - Re-raise as MessageDeliveryError
        # - These should be investigated and fixed
        #
        # FINALLY BLOCK GUARANTEES:
        #
        # These operations ALWAYS execute, regardless of success/failure:
        #
        # 1. Rate limit recording:
        # - Charge against rate limit even if delivery failed
        # - Prevents retry storms when tmux is unavailable
        # - Fair policy: You pay for the attempt, not just success
        #
        # 2. Message logging (inbox delivery):
        # - Always write to agent_messages.log
        # - This is the fallback delivery mechanism
        # - Recipients can read from log even if tmux failed
        # - Provides audit trail of all messaging attempts
        #
        # 3. Delivery status tracking:
        # - Store success/failure in message object
        # - Allows CLI to show real-time delivery status
        # - Enables monitoring and debugging
        #
        # WHY NOT FAIL FAST:
        # We could fail immediately when tmux is unavailable, but we don't because:
        # - File-based inbox is a valid fallback delivery mechanism
        # - Allows messaging to work in more environments
        # - Provides better user experience (partial functionality vs complete failure)
        # - Maintains audit trail even when real-time delivery fails
        #
        # PERFORMANCE NOTES:
        # - Default timeout: 10 seconds for direct messages (generous)
        # - File logging: Usually <1ms (atomic write to log file)
        # - Total time: Dominated by tmux operation (1-10s) when available
        # ========================================================================

        # Track delivery success for logging
        success = False

        try:
            self.delivery.send_to_pane(
                pane_id, formatted_msg, timeout=DIRECT_MESSAGE_TIMEOUT_SECONDS
            )
            success = True
            logger.info(f"Message {message.msg_id} delivered to {recipient_id}")

        except (TmuxError, TmuxSocketError, TmuxPaneNotFoundError, TmuxTimeoutError) as e:
            # Tmux errors are expected in sandboxed environments
            # Don't raise - just log to file and continue
            # Log at INFO level so delivery failures are visible
            logger.info(
                f"Real-time delivery failed for {recipient_id}, saved to inbox: {type(e).__name__}"
            )

        except Exception as e:
            str(e)
            logger.error(
                f"Unexpected error delivering message {message.msg_id} to {recipient_id}: {e}"
            )
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
        max_recipients: int = MAX_BROADCAST_RECIPIENTS,
    ) -> dict[str, bool]:
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
        # Load agent registry with file locking first to get recipient count
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

        # Check rate limit for EACH recipient (prevents broadcast DoS)
        # This ensures broadcasting to N recipients counts as N messages toward the rate limit
        if not self.rate_limiter.check_rate_limit_bulk(sender_id, len(recipients)):
            max_messages = self.rate_limiter.max_messages
            window_seconds = self.rate_limiter.window_seconds
            raise RateLimitExceeded(
                f"Rate limit exceeded for {sender_id}: broadcasting to {len(recipients)} recipients "
                f"would exceed {max_messages} msg/{window_seconds}s limit. "
                f"Please wait before sending more messages."
            )

        logger.info(f"Broadcasting to {len(recipients)} recipients: {', '.join(recipients)}")

        # Create message
        try:
            message = Message(
                sender_id=sender_id,
                timestamp=datetime.now(),
                msg_type=msg_type,
                content=content,
                recipients=recipients,
            )
        except ValueError as e:
            raise MessageDeliveryError(f"Invalid broadcast message data: {e}") from e

        # Sign the message for authentication
        message.sign()

        # Format message once for efficiency
        formatted_msg = message.format_for_display()

        # ========================================================================
        # BROADCAST DELIVERY LOOP WITH FAULT TOLERANCE
        # ========================================================================
        # This implements a "best-effort" broadcast delivery strategy that attempts
        # to deliver to all recipients while gracefully handling failures.
        #
        # WHY NOT STOP ON FIRST FAILURE:
        # Unlike direct messaging where one recipient failure should abort, broadcasts
        # must attempt delivery to ALL recipients even if some fail. This is because:
        # - Partial delivery is better than no delivery
        # - Agent failures are common (panes close, processes crash, tmux issues)
        # - Caller can inspect delivery_status to see which recipients succeeded
        # - Failure of one agent shouldn't prevent others from receiving messages
        #
        # DELIVERY STRATEGY:
        #
        # 1. Sequential delivery (not parallel):
        # We process recipients one at a time, not in parallel, because:
        # - Tmux operations can block/interfere with each other
        # - Sequential processing simplifies error handling
        # - Total broadcast time is still reasonable (<1s for typical swarm sizes)
        # - We can exit early if time budget is exceeded (not currently implemented)
        #
        # 2. Reduced timeout (5s vs 10s):
        # Broadcasts use a shorter timeout (5s) compared to direct messages (10s):
        # - Faster failure detection for unreachable agents
        # - Prevents one slow agent from blocking entire broadcast
        # - With N recipients, total time = N * 5s worst case
        # - 5s is still generous - most operations complete in <100ms
        #
        # 3. Graceful pane lookup:
        # We don't use _get_agent_pane() which raises exceptions. Instead:
        # - Manually look up pane from registry
        # - If pane not found, mark as failed and continue
        # - This prevents cascading failures if registry is stale
        # - Agent may have terminated between validation and delivery
        #
        # 4. Exception handling hierarchy:
        # Different failure modes get different treatment:
        # - TmuxPaneNotFoundError: Agent terminated, mark failed
        # - TmuxSocketError: Tmux unavailable, mark failed but recoverable
        # - TmuxTimeoutError: Agent slow/hung, mark failed to avoid blocking
        # - Exception: Unexpected error, log as error but continue
        #
        # 5. Complete delivery tracking:
        # We maintain delivery_status dict with every recipient:
        # - True: Message successfully delivered to tmux pane
        # - False: Delivery failed for any reason
        # This allows callers to:
        # - Detect partial failures
        # - Retry failed deliveries
        # - Monitor agent health/reachability
        #
        # RATE LIMITING:
        # Rate limit is recorded AFTER delivery loop, counting each recipient:
        # - Each recipient counts as one message toward the rate limit
        # - Prevents broadcast DoS: can't send 10 broadcasts × 100 recipients = 1000 messages
        # - Fair policy: broadcasting to 10 agents costs 10× more than to 1 agent
        # - Recorded even if all deliveries fail (we attempted the broadcast)
        # - Check is done BEFORE delivery using check_rate_limit_bulk()
        #
        # PERFORMANCE CHARACTERISTICS:
        # - Best case (all succeed): ~100ms for 10 recipients
        # - Worst case (all timeout): 5s * N recipients
        # - Typical case (mixed): 1-2s for 10 recipients
        # - Scales linearly with recipient count
        # ========================================================================

        # Send to all recipients, tracking successes and failures
        delivery_status = {}

        for recipient_id in recipients:
            try:
                # Get pane without raising (handle gracefully for broadcast)
                # Prefer stable tmux_pane_id (%N format) if available
                pane_id = None
                for agent in registry.agents:
                    if agent.id == recipient_id and agent.status == "active":
                        pane_id = agent.tmux_pane_id or agent.pane_index
                        break

                if not pane_id:
                    logger.warning(f"Pane not found for recipient {recipient_id}")
                    delivery_status[recipient_id] = False
                    continue

                # Attempt delivery with shorter timeout for broadcasts
                self.delivery.send_to_pane(
                    pane_id, formatted_msg, timeout=BROADCAST_TIMEOUT_SECONDS
                )
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

        # Always record rate limit for EACH recipient (we attempted the broadcast)
        # This ensures broadcasting to N recipients counts as N messages toward the rate limit
        self.rate_limiter.record_message(sender_id, len(recipients))

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
    sender_id: str, recipient_id: str, message_type: MessageType, content: str
) -> Message | None:
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
    sender_id: str, message_type: MessageType, content: str, exclude_self: bool = True
) -> dict[str, bool]:
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
