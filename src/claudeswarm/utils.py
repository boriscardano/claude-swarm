"""Common utilities for Claude Swarm.

This module provides shared utility functions used across
the claudeswarm package, including:
- File I/O helpers (atomic writes, etc.)
- Path manipulation
- JSON serialization/deserialization
- Timestamp formatting
- Error handling utilities
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any

__all__ = [
    "atomic_write",
    "load_json",
    "save_json",
    "format_timestamp",
    "parse_timestamp",
    "get_or_create_secret",
]


def atomic_write(filepath: Path, content: str) -> None:
    """Write content to file atomically using tmp file + rename.

    Args:
        filepath: Path to write to
        content: Content to write

    Raises:
        OSError: If write fails
    """
    import os
    import tempfile

    # Ensure parent directory exists
    filepath.parent.mkdir(parents=True, exist_ok=True)

    # Write to temporary file in same directory
    fd, tmp_path = tempfile.mkstemp(dir=filepath.parent, text=True)
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(content)
        # Atomic rename
        os.replace(tmp_path, filepath)
    except Exception:
        # Clean up temp file if it still exists
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load_json(filepath: Path) -> Any:
    """Load and parse JSON from file.

    Args:
        filepath: Path to JSON file

    Returns:
        Parsed JSON data

    Raises:
        FileNotFoundError: If file doesn't exist
        json.JSONDecodeError: If file contains invalid JSON
    """
    with open(filepath) as f:
        return json.load(f)


def save_json(filepath: Path, data: Any) -> None:
    """Save data to JSON file atomically.

    Args:
        filepath: Path to write to
        data: Data to serialize

    Raises:
        OSError: If write fails
    """
    content = json.dumps(data, indent=2)
    atomic_write(filepath, content)


def format_timestamp(dt: datetime) -> str:
    """Format datetime as ISO 8601 string.

    Args:
        dt: Datetime to format

    Returns:
        ISO 8601 formatted string
    """
    return dt.isoformat()


def parse_timestamp(ts: str) -> datetime:
    """Parse ISO 8601 timestamp string.

    Args:
        ts: Timestamp string

    Returns:
        Parsed datetime

    Raises:
        ValueError: If timestamp format is invalid
    """
    return datetime.fromisoformat(ts)


def get_or_create_secret(secret_file: Path = None) -> bytes:
    """Get or create a shared secret for HMAC message authentication.

    The secret is stored in ~/.claude-swarm/secret by default.
    If the file doesn't exist, a new cryptographically secure secret is generated.

    Args:
        secret_file: Path to secret file (default: ~/.claude-swarm/secret)

    Returns:
        The shared secret as bytes

    Raises:
        OSError: If secret file cannot be read or written
    """
    if secret_file is None:
        secret_dir = Path.home() / ".claude-swarm"
        secret_file = secret_dir / "secret"

    # Ensure directory exists
    secret_file.parent.mkdir(parents=True, exist_ok=True)

    # If secret exists, read it
    if secret_file.exists():
        try:
            with open(secret_file, 'rb') as f:
                secret = f.read()
            # Validate secret is not empty
            if len(secret) < 32:
                raise ValueError("Secret file is too short (< 32 bytes)")
            return secret
        except Exception as e:
            # If we can't read the secret, generate a new one
            pass

    # Generate new secret (256 bits = 32 bytes)
    secret = secrets.token_bytes(32)

    # Write secret to file with restrictive permissions
    try:
        # Create file with mode 0o600 (read/write for owner only)
        with open(secret_file, 'wb') as f:
            f.write(secret)
        # Ensure file has correct permissions
        secret_file.chmod(0o600)
    except Exception as e:
        raise OSError(f"Failed to write secret file: {e}")

    return secret
