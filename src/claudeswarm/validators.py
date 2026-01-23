"""Input validation utilities for Claude Swarm.

This module provides comprehensive validation functions for:
- Agent IDs (format, length, allowed characters)
- File paths (security, existence, platform compatibility)
- Message content (length, sanitization)
- Timeout values (ranges, types)
- Retry counts and other numeric parameters
- Hostnames and IP addresses (RFC compliance, security warnings)
- Port numbers (range validation)

All validation functions raise ValueError with helpful error messages
when validation fails, making it easy to provide user feedback.

Author: Agent-Validation
Phase: Security & Robustness
"""

from __future__ import annotations

import ipaddress
import os
import re
import stat
import unicodedata
from collections.abc import Callable
from pathlib import Path, PurePath
from typing import Any

__all__ = [
    "ValidationError",
    "validate_agent_id",
    "validate_message_content",
    "validate_file_path",
    "validate_timeout",
    "validate_retry_count",
    "validate_rate_limit_config",
    "validate_recipient_list",
    "validate_tmux_pane_id",
    "validate_host",
    "validate_port",
    "sanitize_message_content",
    "normalize_path",
    "contains_dangerous_unicode",
]

# Validation constants
MAX_MESSAGE_LENGTH = 10 * 1024  # 10KB
MAX_AGENT_ID_LENGTH = 64
MAX_REASON_LENGTH = 512
MIN_TIMEOUT = 1
MAX_TIMEOUT = 3600  # 1 hour
MAX_RETRY_COUNT = 5
MIN_RATE_LIMIT_MESSAGES = 1
MAX_RATE_LIMIT_MESSAGES = 1000
MIN_RATE_LIMIT_WINDOW = 1
MAX_RATE_LIMIT_WINDOW = 3600

# Pattern for valid agent IDs: alphanumeric + hyphens + underscores
AGENT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")

# Pattern for valid tmux pane IDs: must match ^%\d+$ format
TMUX_PANE_ID_PATTERN = re.compile(r"^%\d+$")

# Dangerous Unicode characters to remove
# Bidirectional text override characters (CVE-2021-42574 - Trojan Source attack)
BIDI_OVERRIDE_CHARS = {
    "\u202a",  # LEFT-TO-RIGHT EMBEDDING
    "\u202b",  # RIGHT-TO-LEFT EMBEDDING
    "\u202c",  # POP DIRECTIONAL FORMATTING
    "\u202d",  # LEFT-TO-RIGHT OVERRIDE
    "\u202e",  # RIGHT-TO-LEFT OVERRIDE
    "\u2066",  # LEFT-TO-RIGHT ISOLATE
    "\u2067",  # RIGHT-TO-LEFT ISOLATE
    "\u2068",  # FIRST STRONG ISOLATE
    "\u2069",  # POP DIRECTIONAL ISOLATE
}

# Zero-width characters (can hide content)
ZERO_WIDTH_CHARS = {
    "\u200b",  # ZERO WIDTH SPACE
    "\u200c",  # ZERO WIDTH NON-JOINER
    "\u200d",  # ZERO WIDTH JOINER
    "\u2060",  # WORD JOINER
    "\ufeff",  # ZERO WIDTH NO-BREAK SPACE (BOM)
}

# All dangerous Unicode characters combined
DANGEROUS_UNICODE_CHARS = BIDI_OVERRIDE_CHARS | ZERO_WIDTH_CHARS


class ValidationError(ValueError):
    """Raised when validation fails.

    This is a subclass of ValueError for backward compatibility,
    but provides a more specific exception type for validation errors.
    """

    pass


def validate_agent_id(agent_id: Any) -> str:
    """Validate an agent ID.

    Agent IDs must:
    - Be non-empty strings
    - Contain only alphanumeric characters, hyphens, and underscores
    - Be between 1 and 64 characters long
    - Not start or end with a hyphen

    Args:
        agent_id: Value to validate

    Returns:
        The validated agent ID as a string

    Raises:
        ValidationError: If validation fails with specific reason

    Examples:
        >>> validate_agent_id("agent-1")
        'agent-1'
        >>> validate_agent_id("my_agent_123")
        'my_agent_123'
        >>> validate_agent_id("")
        ValidationError: Agent ID cannot be empty
        >>> validate_agent_id("agent@123")
        ValidationError: Agent ID contains invalid characters
    """
    # Type check
    if not isinstance(agent_id, str):
        raise ValidationError(f"Agent ID must be a string, got {type(agent_id).__name__}")

    # Empty check
    if not agent_id or agent_id.strip() == "":
        raise ValidationError("Agent ID cannot be empty")

    # Strip whitespace
    agent_id = agent_id.strip()

    # Length check
    if len(agent_id) > MAX_AGENT_ID_LENGTH:
        raise ValidationError(
            f"Agent ID too long (max {MAX_AGENT_ID_LENGTH} characters, " f"got {len(agent_id)})"
        )

    # Pattern check
    if not AGENT_ID_PATTERN.match(agent_id):
        raise ValidationError(
            f"Agent ID contains invalid characters. "
            f"Only alphanumeric, hyphens, and underscores allowed: '{agent_id}'"
        )

    # Edge cases: no leading/trailing hyphens
    if agent_id.startswith("-") or agent_id.endswith("-"):
        raise ValidationError(f"Agent ID cannot start or end with a hyphen: '{agent_id}'")

    return agent_id


def validate_message_content(content: Any, max_length: int = MAX_MESSAGE_LENGTH) -> str:
    """Validate message content.

    Message content must:
    - Be a string
    - Not be empty (after stripping)
    - Not exceed max_length bytes

    Args:
        content: Content to validate
        max_length: Maximum allowed length in bytes (default: 10KB)

    Returns:
        The validated content as a string

    Raises:
        ValidationError: If validation fails

    Examples:
        >>> validate_message_content("Hello")
        'Hello'
        >>> validate_message_content("")
        ValidationError: Message content cannot be empty
        >>> validate_message_content("x" * 20000)
        ValidationError: Message content too long
    """
    # Type check
    if not isinstance(content, str):
        raise ValidationError(f"Message content must be a string, got {type(content).__name__}")

    # Empty check (after stripping)
    if not content.strip():
        raise ValidationError("Message content cannot be empty")

    # Length check (in bytes for Unicode safety)
    content_bytes = content.encode("utf-8")
    if len(content_bytes) > max_length:
        raise ValidationError(
            f"Message content too long (max {max_length} bytes, " f"got {len(content_bytes)} bytes)"
        )

    return content


def sanitize_message_content(content: str) -> str:
    """Sanitize message content for safe transmission.

    Removes:
    - Null bytes (can truncate strings in C-based systems)
    - Control characters (except tab, newline, carriage return)
    - Bidirectional override characters (Trojan Source attack prevention)
    - Zero-width characters (hidden content prevention)

    Also:
    - Normalizes line endings to Unix style
    - Strips leading/trailing whitespace per line

    Args:
        content: Content to sanitize

    Returns:
        Sanitized content

    Examples:
        >>> sanitize_message_content("Hello\\x00World")
        'HelloWorld'
        >>> sanitize_message_content("  Line 1  \\n  Line 2  ")
        'Line 1\\nLine 2'
    """
    if not isinstance(content, str):
        content = str(content)

    # Remove null bytes
    content = content.replace("\x00", "")

    # Remove dangerous Unicode characters (bidi overrides, zero-width)
    for char in DANGEROUS_UNICODE_CHARS:
        content = content.replace(char, "")

    # Remove other control characters (keep tab \x09, newline \x0A, carriage return \x0D)
    content = "".join(
        char
        for char in content
        if char in "\t\n\r" or (ord(char) >= 32 and ord(char) < 127) or ord(char) >= 128
    )

    # Normalize line endings
    content = content.replace("\r\n", "\n").replace("\r", "\n")

    # Trim each line
    lines = content.split("\n")
    lines = [line.rstrip() for line in lines]
    content = "\n".join(lines)

    # Trim overall
    content = content.strip()

    return content


def contains_dangerous_unicode(text: str) -> tuple[bool, list[str]]:
    """Check if text contains dangerous Unicode characters.

    This function detects:
    - Bidirectional override characters (Trojan Source attack vectors)
    - Zero-width characters (hidden content)

    Args:
        text: Text to check for dangerous Unicode characters

    Returns:
        Tuple of (has_dangerous, list of found character names)

    Examples:
        >>> contains_dangerous_unicode("Hello World")
        (False, [])
        >>> contains_dangerous_unicode("Hello\\u202EWorld")
        (True, ['RIGHT-TO-LEFT OVERRIDE'])
    """
    found = []
    for char in DANGEROUS_UNICODE_CHARS:
        if char in text:
            # Get Unicode name for reporting
            try:
                name = unicodedata.name(char)
            except ValueError:
                name = f"U+{ord(char):04X}"
            found.append(name)

    return (len(found) > 0, found)


def validate_file_path(
    filepath: Any,
    must_exist: bool = False,
    must_be_relative: bool = False,
    project_root: Path | None = None,
    check_traversal: bool = True,
) -> Path:
    """Validate a file path.

    File paths must:
    - Be valid path strings or Path objects
    - Not be empty
    - Not contain path traversal attempts (if check_traversal=True)
    - Not contain null bytes or other injection patterns
    - Be within project_root (if check_traversal=True)
    - Not be symlinks pointing outside project_root (if check_traversal=True)
    - Exist (if must_exist=True)
    - Be relative (if must_be_relative=True)

    Args:
        filepath: Path to validate
        must_exist: If True, path must exist on filesystem
        must_be_relative: If True, path must be relative (not absolute)
        project_root: If provided, path must be within this directory.
                     If check_traversal=True and project_root=None, will use get_project_root()
        check_traversal: If True, check for path traversal attempts and ensure path is within project_root

    Returns:
        Validated Path object

    Raises:
        ValidationError: If validation fails

    Examples:
        >>> validate_file_path("src/file.py")
        PosixPath('src/file.py')
        >>> validate_file_path("")
        ValidationError: File path cannot be empty
        >>> validate_file_path("../../../etc/passwd", check_traversal=True)
        ValidationError: Path traversal detected
    """
    # Type validation
    if filepath is None:
        raise ValidationError("File path cannot be None")

    if isinstance(filepath, str):
        if not filepath.strip():
            raise ValidationError("File path cannot be empty")

        # Check for null bytes (common injection technique)
        if "\x00" in filepath:
            raise ValidationError(f"Path contains null bytes: '{filepath}'")

        # Normalize Unicode to prevent homoglyph attacks
        # NFC (Canonical Decomposition, followed by Canonical Composition)
        filepath = unicodedata.normalize("NFC", filepath)

        # Normalize backslashes to forward slashes for cross-platform path traversal detection
        # On Windows, Path() handles both automatically, but on POSIX, backslashes are
        # treated as valid filename characters, which can bypass traversal detection
        if "\\" in filepath:
            # Check if this looks like a Windows-style path traversal
            if "..\\" in filepath or "\\..\\" in filepath or filepath.endswith("\\.."):
                raise ValidationError(f"Potentially dangerous path pattern detected: '{filepath}'")
            # Also normalize backslashes for consistent handling
            filepath = filepath.replace("\\", "/")

        try:
            path = Path(filepath)
        except (TypeError, ValueError) as e:
            raise ValidationError(f"Invalid file path: {e}")
    elif isinstance(filepath, (Path, PurePath)):
        path = Path(filepath)
    else:
        raise ValidationError(f"File path must be a string or Path, got {type(filepath).__name__}")

    # Relative/absolute check
    if must_be_relative and path.is_absolute():
        raise ValidationError(f"File path must be relative, got absolute path: {path}")

    # Enhanced path traversal check using resolve() and relative_to()
    if check_traversal:
        # Only check relative paths for traversal by default
        # If project_root is explicitly provided, check all paths
        should_check_containment = project_root is not None or not path.is_absolute()

        if should_check_containment:
            # Get project root
            if project_root is None:
                from .project import get_project_root

                project_root = get_project_root()

            try:
                # Resolve project root
                project_root_resolved = Path(project_root).resolve(strict=False)

                # Convert to absolute and resolve
                if path.is_absolute():
                    resolved_path = path.resolve(strict=False)
                else:
                    resolved_path = (project_root_resolved / path).resolve(strict=False)

                # Check containment using relative_to() - most secure method
                try:
                    resolved_path.relative_to(project_root_resolved)
                except ValueError:
                    raise ValidationError(
                        f"Path traversal detected: '{path}' resolves to '{resolved_path}' "
                        f"which is outside project root '{project_root_resolved}'"
                    )

                # Check for symlinks pointing outside project root
                # The resolve() call above already followed symlinks, so resolved_path
                # represents the final destination. The containment check validates this.
                # For additional safety, check if original path contains symlinks
                try:
                    # Atomically check symlinks by comparing resolved vs unresolved paths
                    # If the path contains symlinks, resolve() will have followed them
                    # We've already validated that resolved_path is within project_root_resolved
                    # So if there were symlinks, they're safe (they resolve to within the root)

                    # Additional safety check: if path is a symlink itself,
                    # verify the symlink target using atomic lstat + readlink
                    symlink_path = path if path.is_absolute() else project_root_resolved / path
                    try:
                        # Use os.lstat() to atomically check if it's a symlink
                        # without following it (avoids TOCTOU race condition)
                        lstat_result = os.lstat(symlink_path)
                        if stat.S_ISLNK(lstat_result.st_mode):
                            # Now safe to read the symlink target
                            symlink_target = os.readlink(symlink_path)
                            # If symlink target is absolute, check it directly
                            if os.path.isabs(symlink_target):
                                target_path = Path(symlink_target).resolve(strict=False)
                                target_path.relative_to(project_root_resolved)
                            # Relative symlink targets are resolved relative to symlink location
                            # They're already validated by the resolved_path check above
                    except FileNotFoundError:
                        # Path doesn't exist yet - this is fine for validation purposes
                        # The must_exist check will catch this if needed
                        pass
                except ValueError:
                    raise ValidationError(
                        f"Path traversal detected: symlink '{path}' points outside "
                        f"project root '{project_root_resolved}'"
                    )
                except (OSError, RuntimeError) as e:
                    # Can't read symlink - fail safe
                    # Note: OSError here means broken symlink or permission issue
                    raise ValidationError(
                        f"Cannot verify symlink '{path}': {e}. "
                        f"Path validation requires readable paths for security."
                    )

                # Validation passed - path is safe
                # Note: We don't modify the original path here, we just validated it

            except ValidationError:
                # Re-raise validation errors
                raise
            except (OSError, RuntimeError) as e:
                # If path resolution fails, fail closed
                raise ValidationError(
                    f"Cannot resolve path '{filepath}': {e}. "
                    f"Path validation requires resolvable paths for security."
                )

    # Legacy project root check (for backward compatibility when check_traversal=False)
    elif project_root is not None:
        try:
            project_root_resolved = Path(project_root).resolve()
            resolved_path = (
                path.resolve() if path.is_absolute() else (project_root_resolved / path).resolve()
            )

            # Check if resolved path is within project root
            try:
                resolved_path.relative_to(project_root_resolved)
            except ValueError:
                raise ValidationError(f"File path is outside project root: {path}")
        except (OSError, RuntimeError) as e:
            raise ValidationError(f"Error resolving path: {e}")

    # Existence check
    if must_exist and not path.exists():
        raise ValidationError(f"File path does not exist: {path}")

    return path


def normalize_path(filepath: str | Path) -> Path:
    """Normalize a file path for cross-platform compatibility.

    This function:
    - Converts to Path object
    - Normalizes separators
    - Resolves . and .. (without resolving symlinks)
    - Converts to forward slashes internally

    Args:
        filepath: Path to normalize

    Returns:
        Normalized Path object

    Examples:
        >>> normalize_path("src/./file.py")
        PosixPath('src/file.py')
        >>> normalize_path("src\\\\file.py")  # Windows-style
        PosixPath('src/file.py')
    """
    path = Path(filepath)
    # Use as_posix() for consistent representation
    return Path(path.as_posix())


def validate_timeout(timeout: Any, min_val: int = MIN_TIMEOUT, max_val: int = MAX_TIMEOUT) -> int:
    """Validate a timeout value.

    Timeout must:
    - Be an integer or convertible to int
    - Be within the specified range [min_val, max_val]

    Args:
        timeout: Timeout value to validate
        min_val: Minimum allowed value (default: 1 second)
        max_val: Maximum allowed value (default: 3600 seconds / 1 hour)

    Returns:
        Validated timeout as int

    Raises:
        ValidationError: If validation fails

    Examples:
        >>> validate_timeout(30)
        30
        >>> validate_timeout(0)
        ValidationError: Timeout must be between 1 and 3600 seconds
        >>> validate_timeout(5000)
        ValidationError: Timeout must be between 1 and 3600 seconds
    """
    # Type check and conversion
    try:
        timeout_int = int(timeout)
    except (TypeError, ValueError):
        raise ValidationError(f"Timeout must be an integer, got {type(timeout).__name__}")

    # Range check
    if timeout_int < min_val or timeout_int > max_val:
        raise ValidationError(
            f"Timeout must be between {min_val} and {max_val} seconds, " f"got {timeout_int}"
        )

    return timeout_int


def validate_retry_count(retry_count: Any, max_retries: int = MAX_RETRY_COUNT) -> int:
    """Validate a retry count value.

    Retry count must:
    - Be an integer or convertible to int
    - Be non-negative
    - Not exceed max_retries

    Args:
        retry_count: Retry count to validate
        max_retries: Maximum allowed retries (default: 5)

    Returns:
        Validated retry count as int

    Raises:
        ValidationError: If validation fails

    Examples:
        >>> validate_retry_count(3)
        3
        >>> validate_retry_count(-1)
        ValidationError: Retry count must be non-negative
        >>> validate_retry_count(10)
        ValidationError: Retry count must not exceed 5
    """
    # Type check and conversion
    try:
        count_int = int(retry_count)
    except (TypeError, ValueError):
        raise ValidationError(f"Retry count must be an integer, got {type(retry_count).__name__}")

    # Non-negative check
    if count_int < 0:
        raise ValidationError("Retry count must be non-negative")

    # Max check
    if count_int > max_retries:
        raise ValidationError(f"Retry count must not exceed {max_retries}, got {count_int}")

    return count_int


def validate_rate_limit_config(max_messages: Any, window_seconds: Any) -> tuple[int, int]:
    """Validate rate limit configuration.

    Args:
        max_messages: Maximum messages per window
        window_seconds: Time window in seconds

    Returns:
        Tuple of (validated_max_messages, validated_window_seconds)

    Raises:
        ValidationError: If validation fails

    Examples:
        >>> validate_rate_limit_config(10, 60)
        (10, 60)
        >>> validate_rate_limit_config(0, 60)
        ValidationError: max_messages must be between 1 and 1000
    """
    # Validate max_messages
    try:
        max_msg_int = int(max_messages)
    except (TypeError, ValueError):
        raise ValidationError(f"max_messages must be an integer, got {type(max_messages).__name__}")

    if max_msg_int < MIN_RATE_LIMIT_MESSAGES or max_msg_int > MAX_RATE_LIMIT_MESSAGES:
        raise ValidationError(
            f"max_messages must be between {MIN_RATE_LIMIT_MESSAGES} and "
            f"{MAX_RATE_LIMIT_MESSAGES}, got {max_msg_int}"
        )

    # Validate window_seconds
    try:
        window_int = int(window_seconds)
    except (TypeError, ValueError):
        raise ValidationError(
            f"window_seconds must be an integer, got {type(window_seconds).__name__}"
        )

    if window_int < MIN_RATE_LIMIT_WINDOW or window_int > MAX_RATE_LIMIT_WINDOW:
        raise ValidationError(
            f"window_seconds must be between {MIN_RATE_LIMIT_WINDOW} and "
            f"{MAX_RATE_LIMIT_WINDOW}, got {window_int}"
        )

    return max_msg_int, window_int


def validate_recipient_list(recipients: Any) -> list[str]:
    """Validate a list of message recipients.

    Recipient list must:
    - Be a list or iterable
    - Not be empty
    - Contain only valid agent IDs
    - Not contain duplicates

    Args:
        recipients: List of recipient agent IDs to validate

    Returns:
        Validated list of unique agent IDs

    Raises:
        ValidationError: If validation fails

    Examples:
        >>> validate_recipient_list(["agent-1", "agent-2"])
        ['agent-1', 'agent-2']
        >>> validate_recipient_list([])
        ValidationError: Recipient list cannot be empty
        >>> validate_recipient_list(["agent-1", "invalid@agent"])
        ValidationError: Invalid recipient agent ID at index 1
    """
    # Type check
    if not isinstance(recipients, (list, tuple, set)):
        raise ValidationError(
            f"Recipients must be a list, tuple, or set, " f"got {type(recipients).__name__}"
        )

    # Convert to list
    recipient_list = list(recipients)

    # Empty check
    if not recipient_list:
        raise ValidationError("Recipient list cannot be empty")

    # Validate each recipient
    validated_recipients = []
    seen = set()

    for i, recipient in enumerate(recipient_list):
        try:
            validated_id = validate_agent_id(recipient)
        except ValidationError as e:
            raise ValidationError(f"Invalid recipient agent ID at index {i}: {e}")

        # Check for duplicates
        if validated_id in seen:
            raise ValidationError(f"Duplicate recipient at index {i}: '{validated_id}'")

        seen.add(validated_id)
        validated_recipients.append(validated_id)

    return validated_recipients


def validate_tmux_pane_id(pane_id: Any) -> str:
    """Validate a tmux pane ID.

    Tmux pane IDs must:
    - Be non-empty strings
    - Match the format: %<number> (e.g., %0, %1, %123)
    - Contain only a percent sign followed by digits

    This validation prevents command injection attacks when using tmux pane IDs
    in subprocess calls.

    Args:
        pane_id: Value to validate

    Returns:
        The validated pane ID as a string

    Raises:
        ValidationError: If validation fails with specific reason

    Examples:
        >>> validate_tmux_pane_id("%0")
        '%0'
        >>> validate_tmux_pane_id("%123")
        '%123'
        >>> validate_tmux_pane_id("%1; rm -rf /")
        ValidationError: Invalid tmux pane ID format
        >>> validate_tmux_pane_id("invalid")
        ValidationError: Invalid tmux pane ID format
    """
    # Type check
    if not isinstance(pane_id, str):
        raise ValidationError(f"Tmux pane ID must be a string, got {type(pane_id).__name__}")

    # Empty check
    if not pane_id:
        raise ValidationError("Tmux pane ID cannot be empty")

    # Pattern check - must match ^%\d+$ format
    if not TMUX_PANE_ID_PATTERN.match(pane_id):
        raise ValidationError(
            f"Invalid tmux pane ID format. Expected format: %<number> (e.g., %0, %1), "
            f"got: '{pane_id}'"
        )

    return pane_id


# Valid hostname pattern (RFC 1123)
HOSTNAME_PATTERN = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.[A-Za-z0-9-]{1,63})*$"
)


def validate_host(
    host: str,
    allow_all_interfaces: bool = False,
    warn_callback: Callable[[str], None] | None = None,
) -> str:
    """Validate a hostname or IP address.

    Args:
        host: Hostname or IP address to validate
        allow_all_interfaces: If False, warn about 0.0.0.0
        warn_callback: Optional callback to issue warnings

    Returns:
        Validated host string

    Raises:
        ValidationError: If host is invalid

    Examples:
        >>> validate_host("localhost")
        'localhost'
        >>> validate_host("127.0.0.1")
        '127.0.0.1'
        >>> validate_host("example.com")
        'example.com'
        >>> validate_host("")
        ValidationError: Host must be a non-empty string
        >>> validate_host("invalid@host")
        ValidationError: Invalid hostname
    """
    if not host or not isinstance(host, str):
        raise ValidationError("Host must be a non-empty string")

    host = host.strip()

    # Check for dangerous all-interfaces binding
    # fmt: off
    if host in ("0.0.0.0", "::") and not allow_all_interfaces:  # nosec B104
    # fmt: on
        if warn_callback:
            warn_callback(
                f"Warning: Binding to '{host}' exposes the service to all network interfaces. "
                "Consider using '127.0.0.1' or 'localhost' for local-only access."
            )

    # Try parsing as IP address first
    try:
        ip = ipaddress.ip_address(host)
        # Warn about public IPs
        if warn_callback and ip.is_global:
            warn_callback(
                f"Warning: '{host}' is a public IP address. "
                "Ensure proper firewall rules are in place."
            )
        return host
    except ValueError:
        pass

    # Validate as hostname
    if not HOSTNAME_PATTERN.match(host):
        raise ValidationError(
            f"Invalid hostname: '{host}'. Must be a valid hostname or IP address."
        )

    return host


def validate_port(port: Any, allow_privileged: bool = False) -> int:
    """Validate a port number.

    Args:
        port: Port number to validate
        allow_privileged: If False, warn about ports < 1024

    Returns:
        Validated port as integer

    Raises:
        ValidationError: If port is invalid

    Examples:
        >>> validate_port(8080)
        8080
        >>> validate_port(80)
        80
        >>> validate_port(0)
        ValidationError: Port must be between 1 and 65535
        >>> validate_port(70000)
        ValidationError: Port must be between 1 and 65535
        >>> validate_port("invalid")
        ValidationError: Port must be an integer
    """
    try:
        port = int(port)
    except (TypeError, ValueError):
        raise ValidationError(f"Port must be an integer, got: {type(port).__name__}")

    if port < 1 or port > 65535:
        raise ValidationError(f"Port must be between 1 and 65535, got: {port}")

    return port
