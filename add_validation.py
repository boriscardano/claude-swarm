#!/usr/bin/env python3
"""Script to add comprehensive validation to all modules.

This script adds validation imports and updates existing validation
logic in messaging.py, locking.py, and ack.py.
"""

import re
from pathlib import Path


def add_validators_to_messaging():
    """Add validators import and validation logic to messaging.py."""
    filepath = Path("src/claudeswarm/messaging.py")
    content = filepath.read_text()

    # Add validators import after utils import
    if "from .validators import" not in content:
        content = content.replace(
            "from .utils import get_or_create_secret",
            """from .utils import get_or_create_secret
from .validators import (
    ValidationError,
    validate_agent_id,
    validate_message_content,
    validate_rate_limit_config,
    validate_recipient_list,
    sanitize_message_content,
)"""
        )

    # Update Message.__post_init__ validation
    old_validation = '''    def __post_init__(self):
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
            self.timestamp = datetime.fromisoformat(self.timestamp)'''

    new_validation = '''    def __post_init__(self):
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
            self.timestamp = datetime.fromisoformat(self.timestamp)'''

    content = content.replace(old_validation, new_validation)

    # Update RateLimiter.__init__ with validation
    old_init = '''    def __init__(self, max_messages: int = 10, window_seconds: int = 60):
        """Initialize rate limiter.

        Args:
            max_messages: Maximum messages allowed per window
            window_seconds: Time window in seconds
        """
        self.max_messages = max_messages
        self.window_seconds = window_seconds
        # Track message timestamps per agent
        self._message_times: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_messages))'''

    new_init = '''    def __init__(self, max_messages: int = 10, window_seconds: int = 60):
        """Initialize rate limiter.

        Args:
            max_messages: Maximum messages allowed per window
            window_seconds: Time window in seconds

        Raises:
            ValidationError: If rate limit configuration is invalid
        """
        # Validate rate limit configuration
        try:
            self.max_messages, self.window_seconds = validate_rate_limit_config(
                max_messages, window_seconds
            )
        except ValidationError as e:
            raise ValueError(f"Invalid rate limit configuration: {e}")

        # Track message timestamps per agent
        self._message_times: Dict[str, deque] = defaultdict(lambda: deque(maxlen=self.max_messages))'''

    content = content.replace(old_init, new_init)

    filepath.write_text(content)
    print(f"Updated {filepath}")


def add_validators_to_locking():
    """Add validators import and validation logic to locking.py."""
    filepath = Path("src/claudeswarm/locking.py")
    content = filepath.read_text()

    # Add validators import after pathlib
    if "from .validators import" not in content:
        imports_section = """from pathlib import Path
from typing import Optional"""
        new_imports = """from pathlib import Path
from typing import Optional

from .validators import (
    ValidationError,
    validate_agent_id,
    validate_file_path,
    validate_timeout,
    normalize_path,
)"""
        content = content.replace(imports_section, new_imports)

    # Update acquire_lock to validate inputs
    # This is complex, so we'll add validation at the start of the method
    acquire_lock_start = '''    def acquire_lock(
        self,
        filepath: str,
        agent_id: str,
        reason: str = "",
        timeout: int = STALE_LOCK_TIMEOUT,
    ) -> tuple[bool, Optional[LockConflict]]:
        """Acquire a lock on a file.

        Args:
            filepath: Path to the file to lock (can be a glob pattern)
            agent_id: Unique identifier of the agent acquiring the lock
            reason: Human-readable explanation for the lock
            timeout: Timeout in seconds for considering locks stale

        Returns:
            Tuple of (success, conflict):
                - (True, None) if lock acquired successfully
                - (False, LockConflict) if lock held by another agent
        """
        lock_path = self._get_lock_path(filepath)'''

    new_acquire_lock_start = '''    def acquire_lock(
        self,
        filepath: str,
        agent_id: str,
        reason: str = "",
        timeout: int = STALE_LOCK_TIMEOUT,
    ) -> tuple[bool, Optional[LockConflict]]:
        """Acquire a lock on a file.

        Args:
            filepath: Path to the file to lock (can be a glob pattern)
            agent_id: Unique identifier of the agent acquiring the lock
            reason: Human-readable explanation for the lock
            timeout: Timeout in seconds for considering locks stale

        Returns:
            Tuple of (success, conflict):
                - (True, None) if lock acquired successfully
                - (False, LockConflict) if lock held by another agent

        Raises:
            ValidationError: If inputs are invalid
        """
        # Validate inputs
        agent_id = validate_agent_id(agent_id)
        timeout = validate_timeout(timeout)
        # Normalize filepath for cross-platform compatibility
        filepath = str(normalize_path(filepath))

        lock_path = self._get_lock_path(filepath)'''

    content = content.replace(acquire_lock_start, new_acquire_lock_start)

    filepath.write_text(content)
    print(f"Updated {filepath}")


def add_validators_to_ack():
    """Add validators import and validation logic to ack.py."""
    filepath = Path("src/claudeswarm/ack.py")
    content = filepath.read_text()

    # Add validators import
    if "from .validators import" not in content:
        content = content.replace(
            "from .utils import load_json, save_json",
            """from .utils import load_json, save_json
from .validators import (
    ValidationError,
    validate_agent_id,
    validate_retry_count,
    validate_timeout,
    validate_message_content,
)"""
        )

    # Update send_with_ack to validate inputs
    old_send_with_ack = '''        if not sender_id or not recipient_id:
            raise ValueError("sender_id and recipient_id cannot be empty")

        # Prefix content with [REQUIRES-ACK]'''

    new_send_with_ack = '''        # Validate inputs
        try:
            sender_id = validate_agent_id(sender_id)
            recipient_id = validate_agent_id(recipient_id)
            content = validate_message_content(content)
            timeout = validate_timeout(timeout, min_val=1, max_val=300)
        except ValidationError as e:
            raise ValueError(f"Invalid input: {e}")

        # Prefix content with [REQUIRES-ACK]'''

    content = content.replace(old_send_with_ack, new_send_with_ack)

    filepath.write_text(content)
    print(f"Updated {filepath}")


def main():
    """Apply all validation updates."""
    print("Adding comprehensive validation to Claude Swarm modules...")
    print()

    try:
        add_validators_to_messaging()
        add_validators_to_locking()
        add_validators_to_ack()
        print()
        print("All validation updates applied successfully!")
        print()
        print("Next steps:")
        print("1. Run tests: pytest tests/")
        print("2. Check for any issues: python -m src.claudeswarm.messaging")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
