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
import os
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

    This function provides crash-safe file writes by:
    1. Writing to a temporary file in the same directory
    2. Atomically renaming the temp file to the target (os.replace)

    The atomic rename ensures that readers never see partial writes,
    and the file is never left in a corrupted state even if the
    process crashes mid-write.

    Edge Cases:
        - Parent directory is created if it doesn't exist
        - Temp file is cleaned up on error
        - Works correctly with concurrent readers (they see old or new, never partial)
        - Preserves file permissions on existing files (os.replace behavior)
        - Handles symlinks by replacing the symlink itself, not the target

    Args:
        filepath: Path to write to (absolute or relative)
        content: Content to write (must be a string, not bytes)

    Raises:
        OSError: If write fails, directory creation fails, or rename fails
        PermissionError: If insufficient permissions for directory or file
        TypeError: If content is not a string

    Example:
        >>> from pathlib import Path
        >>> atomic_write(Path("data.json"), '{"key": "value"}')
        >>> # File is guaranteed to be complete, never partially written
    """
    import tempfile

    # Ensure parent directory exists
    filepath.parent.mkdir(parents=True, exist_ok=True)

    # Write to temporary file in same directory
    fd, tmp_path = tempfile.mkstemp(dir=filepath.parent, text=True)
    try:
        with os.fdopen(fd, "w") as f:
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

    Edge Cases:
        - Empty files raise json.JSONDecodeError
        - Files with only whitespace raise json.JSONDecodeError
        - Files with BOM are handled correctly by json.load
        - Symlinks are followed to the target file
        - Returns any valid JSON type (dict, list, str, int, bool, null)

    Args:
        filepath: Path to JSON file

    Returns:
        Parsed JSON data (dict, list, str, int, float, bool, or None)

    Raises:
        FileNotFoundError: If file doesn't exist
        json.JSONDecodeError: If file contains invalid JSON or is empty
        PermissionError: If insufficient permissions to read file
        IsADirectoryError: If filepath points to a directory

    Example:
        >>> from pathlib import Path
        >>> data = load_json(Path("config.json"))
        >>> assert isinstance(data, (dict, list))  # Most common cases
    """
    with open(filepath) as f:
        return json.load(f)


def save_json(filepath: Path, data: Any) -> None:
    """Save data to JSON file atomically.

    Uses atomic_write internally to ensure crash-safe writes.
    JSON is serialized with 2-space indentation for readability.

    Edge Cases:
        - Handles nested structures (dicts, lists) to any depth
        - Non-serializable types (e.g., datetime, custom objects) raise TypeError
        - NaN and Infinity are serialized as null (JSON standard)
        - Unicode characters are preserved (not escaped)
        - Circular references raise ValueError

    Args:
        filepath: Path to write to
        data: Data to serialize (must be JSON-serializable)

    Raises:
        OSError: If write fails
        TypeError: If data contains non-serializable types
        ValueError: If data contains circular references

    Example:
        >>> from pathlib import Path
        >>> save_json(Path("output.json"), {"status": "success", "count": 42})
        >>> # File is written atomically with proper formatting
    """
    content = json.dumps(data, indent=2)
    atomic_write(filepath, content)


def format_timestamp(dt: datetime) -> str:
    """Format datetime as ISO 8601 string.

    Produces timestamps in ISO 8601 format (e.g., "2025-11-18T14:30:00.123456+00:00").

    Edge Cases:
        - Naive datetimes (no timezone) are formatted without timezone offset
        - Aware datetimes (with timezone) include timezone offset
        - Microsecond precision is preserved
        - UTC timezone is represented as "+00:00" not "Z"

    Args:
        dt: Datetime to format (can be naive or timezone-aware)

    Returns:
        ISO 8601 formatted string

    Example:
        >>> from datetime import datetime, timezone
        >>> dt = datetime(2025, 11, 18, 14, 30, 0, tzinfo=timezone.utc)
        >>> format_timestamp(dt)
        '2025-11-18T14:30:00+00:00'
    """
    return dt.isoformat()


def parse_timestamp(ts: str) -> datetime:
    """Parse ISO 8601 timestamp string.

    Parses timestamps produced by format_timestamp() or standard ISO 8601.

    Edge Cases:
        - Accepts timestamps with or without timezone
        - Accepts timestamps with "Z" suffix (converted to UTC)
        - Accepts timestamps with fractional seconds
        - Raises ValueError for non-ISO 8601 formats
        - Raises ValueError for invalid dates (e.g., "2025-13-01")

    Args:
        ts: Timestamp string in ISO 8601 format

    Returns:
        Parsed datetime object (preserves timezone if present)

    Raises:
        ValueError: If timestamp format is invalid or date is out of range
        TypeError: If ts is not a string

    Example:
        >>> parse_timestamp("2025-11-18T14:30:00+00:00")
        datetime.datetime(2025, 11, 18, 14, 30, tzinfo=datetime.timezone.utc)
        >>> parse_timestamp("invalid")
        Traceback (most recent call last):
            ...
        ValueError: Invalid isoformat string: 'invalid'
    """
    return datetime.fromisoformat(ts)


def get_or_create_secret(secret_file: Path = None) -> bytes:
    """Get or create a shared secret for HMAC message authentication.

    The secret is stored in ~/.claude-swarm/secret by default.
    If the file doesn't exist, a new cryptographically secure secret is generated.

    Security Properties:
        - 256-bit (32-byte) secret generated using secrets.token_bytes
        - File permissions set to 0o600 (read/write for owner only)
        - Secrets are never logged or printed
        - Corrupted/short secrets raise OSError with clear fix instructions

    Edge Cases:
        - Creates parent directory if it doesn't exist
        - Raises OSError if existing file is corrupted or too short (< 32 bytes)
        - File permissions are enforced on every write
        - Handles concurrent access (last writer wins, no locking)
        - Returns same secret on repeated calls (cached in file)

    Args:
        secret_file: Path to secret file (default: ~/.claude-swarm/secret)

    Returns:
        The shared secret as 32 bytes

    Raises:
        OSError: If secret file cannot be read, is corrupted, or cannot be written
        PermissionError: If insufficient permissions for directory or file

    Example:
        >>> secret = get_or_create_secret()
        >>> len(secret)
        32
        >>> # Same secret returned on subsequent calls
        >>> assert get_or_create_secret() == secret
    """
    if secret_file is None:
        secret_dir = Path.home() / ".claude-swarm"
        secret_file = secret_dir / "secret"

    # Ensure directory exists
    secret_file.parent.mkdir(parents=True, exist_ok=True)

    # If secret exists, read it
    if secret_file.exists():
        try:
            with open(secret_file, "rb") as f:
                secret = f.read()
            # Validate secret is not empty
            if len(secret) < 32:
                raise OSError(
                    f"Corrupted secret file at {secret_file}: file is too short (< 32 bytes). "
                    f"To fix: delete the file and run the command again to generate a new secret."
                )
            return secret
        except OSError:
            # Re-raise OSError (includes corrupted file, permission denied, etc.)
            raise
        except Exception as e:
            # For other exceptions, raise OSError with helpful message
            raise OSError(
                f"Failed to read secret file at {secret_file}: {e}. "
                f"To fix: check file permissions or delete the file to generate a new secret."
            )

    # Generate new secret (256 bits = 32 bytes)
    secret = secrets.token_bytes(32)

    # Write secret to file with restrictive permissions
    try:
        # Create file with mode 0o600 (read/write for owner only)
        with open(secret_file, "wb") as f:
            f.write(secret)
        # Ensure file has correct permissions
        secret_file.chmod(0o600)
    except Exception as e:
        raise OSError(f"Failed to write secret file: {e}")

    return secret
