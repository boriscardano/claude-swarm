"""Message acknowledgment and retry system for Claude Swarm.

This module provides functionality to:
- Send messages that require acknowledgment
- Track pending acknowledgments
- Implement automatic retry with exponential backoff
- Escalate unacknowledged messages to all agents
- Match received ACKs to pending messages

The ACK system ensures critical messages are received and acknowledged,
with automatic retry and escalation if no response is received.

Author: Agent-4
Phase: Phase 2
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .logging_config import get_logger
from .messaging import MessageType, broadcast_message, send_message
from .utils import load_json, save_json
from .validators import (
    ValidationError,
    validate_agent_id,
    validate_retry_count,
    validate_timeout,
    validate_message_content,
)

__all__ = [
    "PendingAck",
    "AckSystem",
    "send_with_ack",
    "acknowledge_message",
    "check_pending_acks",
    "receive_ack",
    "get_ack_system",
]

# Configure logging
logger = get_logger(__name__)


@dataclass
class PendingAck:
    """Represents a message awaiting acknowledgment.

    Attributes:
        msg_id: Unique message identifier
        sender_id: Agent who sent the message
        recipient_id: Agent who should acknowledge
        message: The original message (as dict for JSON serialization)
        sent_at: When the message was first sent (ISO string)
        retry_count: Number of retry attempts made
        next_retry_at: When to retry if no ACK received (ISO string)
    """

    msg_id: str
    sender_id: str
    recipient_id: str
    message: dict  # Store message as dict for JSON serialization
    sent_at: str  # ISO timestamp
    retry_count: int = 0
    next_retry_at: str = ""  # ISO timestamp

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> PendingAck:
        """Create PendingAck from dictionary."""
        return cls(**data)

    def get_sent_datetime(self) -> datetime:
        """Get sent_at as datetime object."""
        return datetime.fromisoformat(self.sent_at)

    def get_next_retry_datetime(self) -> datetime:
        """Get next_retry_at as datetime object."""
        return datetime.fromisoformat(self.next_retry_at)


class AckSystem:
    """Main acknowledgment system for Claude Swarm.

    Manages:
    - Tracking pending ACKs in PENDING_ACKS.json
    - Retry logic with exponential backoff (30s, 60s, 120s)
    - Escalation after max retries
    - ACK reception and matching
    """

    # Retry configuration
    MAX_RETRIES = 3
    RETRY_DELAYS = [30, 60, 120]  # Exponential backoff in seconds

    def __init__(self, pending_file: Optional[Path] = None):
        """Initialize ACK system.

        Args:
            pending_file: Path to PENDING_ACKS.json (default: ./PENDING_ACKS.json)
        """
        self.pending_file = pending_file or Path("./PENDING_ACKS.json")
        self._lock = threading.Lock()
        self._ensure_pending_file()

    def _ensure_pending_file(self) -> None:
        """Ensure PENDING_ACKS.json exists with version tracking."""
        if not self.pending_file.exists():
            save_json(self.pending_file, {"version": 0, "pending_acks": []})
            logger.info(f"Created pending ACKs file at {self.pending_file}")

    def _load_pending_acks(self) -> tuple[list[PendingAck], int]:
        """Load pending ACKs from file with version number.

        Returns:
            Tuple of (list of PendingAck objects, version number)
        """
        try:
            data = load_json(self.pending_file)
            # Support legacy files without version field
            version = data.get("version", 0)
            acks_data = data.get("pending_acks", [])
            return [PendingAck.from_dict(ack) for ack in acks_data], version
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Error loading pending ACKs: {e}")
            return [], 0

    def _save_pending_acks(
        self, acks: list[PendingAck], expected_version: Optional[int] = None
    ) -> bool:
        """Save pending ACKs to file with optimistic locking.

        Uses version-based optimistic locking to prevent race conditions.
        If expected_version is provided, only saves if current version matches.

        Args:
            acks: List of PendingAck objects to save
            expected_version: Expected version number (for optimistic locking)

        Returns:
            True if save succeeded, False if version mismatch occurred
        """
        # If version checking is enabled, verify version matches
        if expected_version is not None:
            current_acks, current_version = self._load_pending_acks()
            if current_version != expected_version:
                logger.debug(
                    f"Version mismatch: expected {expected_version}, "
                    f"found {current_version}. Aborting save."
                )
                return False
            new_version = current_version + 1
        else:
            # No version check requested, just increment from current
            _, current_version = self._load_pending_acks()
            new_version = current_version + 1

        data = {"version": new_version, "pending_acks": [ack.to_dict() for ack in acks]}
        save_json(self.pending_file, data)
        logger.debug(f"Saved pending ACKs with version {new_version}")
        return True

    def send_with_ack(
        self,
        sender_id: str,
        recipient_id: str,
        msg_type: MessageType,
        content: str,
        timeout: int = 30,
    ) -> Optional[str]:
        """Send a message that requires acknowledgment.

        The message will be sent with [REQUIRES-ACK] prefix and tracked
        for automatic retry if no acknowledgment is received.

        Args:
            sender_id: ID of sending agent
            recipient_id: ID of receiving agent
            msg_type: Type of message
            content: Message content
            timeout: Seconds to wait before first retry (default: 30)

        Returns:
            Message ID for tracking, or None if send failed

        Raises:
            ValueError: If sender_id or recipient_id is empty
        """
        # Validate inputs
        try:
            sender_id = validate_agent_id(sender_id)
            recipient_id = validate_agent_id(recipient_id)
            content = validate_message_content(content)
            timeout = validate_timeout(timeout, min_val=1, max_val=300)
        except ValidationError as e:
            raise ValueError(f"Invalid input: {e}")

        # Prefix content with [REQUIRES-ACK]
        ack_content = f"[REQUIRES-ACK] {content}"

        # Calculate next retry time
        next_retry = datetime.now() + timedelta(seconds=timeout)

        # Create pending ACK entry BEFORE sending (to avoid race condition)
        # We'll use a temporary msg_id that we'll update after send
        temp_msg_id = f"temp-{sender_id}-{datetime.now().timestamp()}"
        pending_ack = PendingAck(
            msg_id=temp_msg_id,
            sender_id=sender_id,
            recipient_id=recipient_id,
            message={},  # Will be filled after send
            sent_at=datetime.now().isoformat(),
            retry_count=0,
            next_retry_at=next_retry.isoformat(),
        )

        # Add to tracking BEFORE sending
        with self._lock:
            acks, version = self._load_pending_acks()
            acks.append(pending_ack)
            self._save_pending_acks(acks, expected_version=version)

        # Send the message
        try:
            message = send_message(sender_id, recipient_id, msg_type, ack_content)

            if not message:
                logger.error(f"Failed to send message from {sender_id} to {recipient_id}")
                # Clean up the pending ACK since send failed
                with self._lock:
                    acks, version = self._load_pending_acks()
                    acks = [ack for ack in acks if ack.msg_id != temp_msg_id]
                    self._save_pending_acks(acks, expected_version=version)
                return None

            # Update the pending ACK with actual message info
            with self._lock:
                acks, version = self._load_pending_acks()
                for ack in acks:
                    if ack.msg_id == temp_msg_id:
                        ack.msg_id = message.msg_id
                        ack.message = message.to_dict()
                        break
                self._save_pending_acks(acks, expected_version=version)

            logger.info(
                f"Message {message.msg_id} sent with ACK requirement: "
                f"{sender_id} -> {recipient_id}"
            )

            return message.msg_id

        except Exception as e:
            logger.error(f"Exception while sending message: {e}")
            # Clean up the pending ACK
            with self._lock:
                acks, version = self._load_pending_acks()
                acks = [ack for ack in acks if ack.msg_id != temp_msg_id]
                self._save_pending_acks(acks, expected_version=version)
            raise

    def receive_ack(self, msg_id: str, agent_id: str) -> bool:
        """Process received acknowledgment for a message.

        Matches the ACK to a pending entry and removes it from tracking.

        Args:
            msg_id: ID of message being acknowledged
            agent_id: ID of agent acknowledging

        Returns:
            True if ACK was matched and removed, False if not found
        """
        with self._lock:
            acks, version = self._load_pending_acks()

            # Find matching pending ACK
            for i, ack in enumerate(acks):
                if ack.msg_id == msg_id:
                    # Verify acknowledger is the expected recipient
                    if ack.recipient_id != agent_id:
                        logger.warning(
                            f"ACK from unexpected agent: expected {ack.recipient_id}, "
                            f"got {agent_id} for message {msg_id}"
                        )
                        # Still accept the ACK

                    # Remove from pending
                    acks.pop(i)
                    self._save_pending_acks(acks, expected_version=version)

                    logger.info(
                        f"ACK received for message {msg_id} from {agent_id}, "
                        f"removed from pending"
                    )
                    return True

            logger.warning(f"No pending ACK found for message {msg_id}")
            return False

    def check_pending_acks(self, agent_id: Optional[str] = None) -> list[PendingAck]:
        """Check for messages awaiting acknowledgment.

        Args:
            agent_id: If provided, filter to messages from this agent

        Returns:
            List of pending acknowledgments
        """
        acks, _ = self._load_pending_acks()

        if agent_id:
            acks = [ack for ack in acks if ack.sender_id == agent_id]

        return acks

    def process_retries(self) -> int:
        """Process pending ACKs and retry/escalate as needed.

        This should be called periodically (e.g., every 10 seconds)
        to check for timed-out messages and trigger retries or escalation.

        Uses optimistic locking to prevent race conditions with receive_ack().
        If version conflict detected, retries the entire operation.

        Returns:
            Number of messages retried or escalated
        """
        max_attempts = 5  # Maximum retry attempts for version conflicts

        for attempt in range(max_attempts):
            now = datetime.now()
            processed_count = 0

            # Load ACKs with version - hold lock only during load
            with self._lock:
                acks, version = self._load_pending_acks()

            # Process ACKs outside the lock (this can take seconds)
            updated_acks = []

            for ack in acks:
                next_retry_dt = ack.get_next_retry_datetime()

                # Check if retry is needed
                if now >= next_retry_dt:
                    if ack.retry_count < self.MAX_RETRIES:
                        # Retry the message (this can take time)
                        self._retry_message(ack)
                        ack.retry_count += 1

                        # Check if this was the last retry
                        if ack.retry_count >= self.MAX_RETRIES:
                            # Max retries reached, escalate immediately
                            self._escalate_message(ack)
                            # Don't add back to pending
                        else:
                            # Calculate next retry time with exponential backoff
                            delay = self.RETRY_DELAYS[ack.retry_count]
                            ack.next_retry_at = (now + timedelta(seconds=delay)).isoformat()
                            updated_acks.append(ack)

                        processed_count += 1
                    else:
                        # Max retries already exceeded, escalate
                        self._escalate_message(ack)
                        processed_count += 1
                        # Don't add back to pending
                else:
                    # Not yet time to retry
                    updated_acks.append(ack)

            # Try to save - hold lock only during save
            with self._lock:
                if self._save_pending_acks(updated_acks, expected_version=version):
                    # Save succeeded
                    logger.debug(f"process_retries: saved on attempt {attempt + 1}")
                    return processed_count
                else:
                    # Version conflict - another process modified the file
                    logger.info(
                        f"process_retries: version conflict on attempt {attempt + 1}, "
                        f"retrying..."
                    )
                    # Loop will retry with fresh data

        # If we get here, all retry attempts failed
        logger.error(
            f"process_retries: failed to save after {max_attempts} attempts "
            f"due to version conflicts"
        )
        return 0

    def _retry_message(self, ack: PendingAck) -> None:
        """Retry sending a message.

        Args:
            ack: PendingAck entry to retry
        """
        logger.info(
            f"Retrying message {ack.msg_id} (attempt {ack.retry_count + 1}/{self.MAX_RETRIES})"
        )

        # Recreate message from stored dict
        msg_dict = ack.message
        retry_content = f"[RETRY-{ack.retry_count + 1}] {msg_dict['content']}"

        # Send retry
        send_message(
            ack.sender_id,
            ack.recipient_id,
            MessageType(msg_dict["msg_type"]),
            retry_content,
        )

    def _escalate_message(self, ack: PendingAck) -> None:
        """Escalate an unacknowledged message to all agents.

        After max retries, broadcasts the message to all agents
        requesting assistance.

        Args:
            ack: PendingAck entry to escalate
        """
        logger.warning(
            f"Escalating unacknowledged message {ack.msg_id} after "
            f"{self.MAX_RETRIES} retries"
        )

        msg_dict = ack.message
        escalation_content = (
            f"[UNACKNOWLEDGED] Message to {ack.recipient_id} unacknowledged "
            f"after {self.MAX_RETRIES} attempts. Original: {msg_dict['content']}"
        )

        # Broadcast to all agents
        broadcast_message(
            ack.sender_id,
            MessageType(msg_dict["msg_type"]),
            escalation_content,
            exclude_self=False,  # Include sender in escalation
        )

    def get_pending_count(self, agent_id: Optional[str] = None) -> int:
        """Get count of pending ACKs.

        Args:
            agent_id: If provided, count only messages from this agent

        Returns:
            Number of pending acknowledgments
        """
        acks = self.check_pending_acks(agent_id)
        return len(acks)

    def clear_pending_acks(self, agent_id: Optional[str] = None) -> int:
        """Clear pending ACKs (for testing/admin purposes).

        Args:
            agent_id: If provided, clear only messages from this agent

        Returns:
            Number of ACKs cleared
        """
        with self._lock:
            acks, version = self._load_pending_acks()

            if agent_id:
                filtered = [ack for ack in acks if ack.sender_id != agent_id]
                cleared = len(acks) - len(filtered)
                self._save_pending_acks(filtered, expected_version=version)
            else:
                cleared = len(acks)
                self._save_pending_acks([], expected_version=version)

            logger.info(f"Cleared {cleared} pending ACKs")
            return cleared


# Module-level singleton instance
_default_ack_system: Optional[AckSystem] = None
_system_lock = threading.Lock()


def get_ack_system() -> AckSystem:
    """Get or create the default AckSystem instance.

    Returns:
        Singleton AckSystem instance
    """
    global _default_ack_system
    if _default_ack_system is None:
        with _system_lock:
            if _default_ack_system is None:
                _default_ack_system = AckSystem()
    return _default_ack_system


# Module-level convenience functions


def send_with_ack(
    sender_id: str,
    recipient_id: str,
    msg_type: MessageType,
    content: str,
    timeout: int = 30,
) -> str | None:
    """Send a message that requires acknowledgment.

    Args:
        sender_id: ID of sending agent
        recipient_id: ID of receiving agent
        msg_type: Type of message
        content: Message content
        timeout: Seconds to wait before first retry

    Returns:
        Message ID for tracking, or None if send failed

    Raises:
        ValueError: If sender_id or recipient_id is invalid
    """
    system = get_ack_system()
    return system.send_with_ack(sender_id, recipient_id, msg_type, content, timeout)


def acknowledge_message(msg_id: str, agent_id: str) -> bool:
    """Acknowledge receipt of a message.

    Args:
        msg_id: ID of message to acknowledge
        agent_id: ID of agent acknowledging

    Returns:
        True if acknowledgment recorded, False if message not found
    """
    system = get_ack_system()
    return system.receive_ack(msg_id, agent_id)


def receive_ack(msg_id: str, agent_id: str) -> bool:
    """Alias for acknowledge_message for clarity in some contexts.

    Args:
        msg_id: ID of message to acknowledge
        agent_id: ID of agent acknowledging

    Returns:
        True if acknowledgment recorded, False if message not found
    """
    return acknowledge_message(msg_id, agent_id)


def check_pending_acks(agent_id: Optional[str] = None) -> list[PendingAck]:
    """Check for messages awaiting acknowledgment.

    Args:
        agent_id: If provided, filter to messages from this agent

    Returns:
        List of pending acknowledgments
    """
    system = get_ack_system()
    return system.check_pending_acks(agent_id)


def process_pending_retries() -> int:
    """Process pending ACKs and trigger retries/escalation as needed.

    Should be called periodically to maintain the retry system.

    Returns:
        Number of messages processed (retried or escalated)
    """
    system = get_ack_system()
    return system.process_retries()
