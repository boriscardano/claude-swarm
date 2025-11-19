"""
Security utilities for cloud components.

Provides input validation, sanitization, and security helpers
to prevent common vulnerabilities (command injection, XSS, etc.).
"""

import re
import shlex
from typing import Any, Optional


class ValidationError(ValueError):
    """Raised when input validation fails."""

    pass


def validate_sandbox_id(sandbox_id: str) -> str:
    """
    Validate E2B sandbox ID format.

    Ensures sandbox ID only contains safe characters to prevent
    command injection and path traversal attacks.

    Args:
        sandbox_id: The sandbox ID to validate

    Returns:
        The validated sandbox ID

    Raises:
        ValidationError: If sandbox ID format is invalid

    Example:
        ```python
        safe_id = validate_sandbox_id("e2b-abc123-def456")  # OK
        safe_id = validate_sandbox_id("../../etc/passwd")   # Raises ValidationError
        ```
    """
    if not sandbox_id:
        raise ValidationError("Sandbox ID cannot be empty")

    # Allow alphanumeric, hyphens, and underscores only
    if not re.match(r'^[a-zA-Z0-9_-]+$', sandbox_id):
        raise ValidationError(
            f"Invalid sandbox ID '{sandbox_id}'. "
            "Must contain only alphanumeric characters, hyphens, and underscores."
        )

    # Prevent excessive length
    if len(sandbox_id) > 128:
        raise ValidationError(f"Sandbox ID too long (max 128 characters): {len(sandbox_id)}")

    return sandbox_id


def validate_num_agents(num_agents: Any) -> int:
    """
    Validate number of agents parameter.

    Args:
        num_agents: Number of agents to create

    Returns:
        Validated integer number of agents

    Raises:
        ValidationError: If num_agents is invalid

    Example:
        ```python
        count = validate_num_agents(4)        # OK
        count = validate_num_agents("4")      # OK (converts)
        count = validate_num_agents(999)      # Raises ValidationError (too many)
        count = validate_num_agents("../../") # Raises ValidationError
        ```
    """
    try:
        num = int(num_agents)
    except (ValueError, TypeError):
        raise ValidationError(
            f"Invalid num_agents value '{num_agents}'. Must be an integer."
        )

    if num < 1:
        raise ValidationError(f"num_agents must be >= 1, got {num}")

    if num > 100:
        raise ValidationError(
            f"num_agents too high ({num}). Maximum is 100 to prevent resource exhaustion."
        )

    return num


def validate_git_url(url: str) -> str:
    """
    Validate Git repository URL.

    Ensures URL is safe and prevents command injection through git clone.

    Args:
        url: Git repository URL

    Returns:
        Validated URL

    Raises:
        ValidationError: If URL format is invalid or unsafe

    Example:
        ```python
        url = validate_git_url("https://github.com/user/repo.git")  # OK
        url = validate_git_url("git@github.com:user/repo.git")      # OK
        url = validate_git_url("file:///etc/passwd")                # Raises ValidationError
        ```
    """
    if not url:
        raise ValidationError("Git URL cannot be empty")

    # Only allow https:// and git@ URLs
    allowed_prefixes = ('https://', 'git@')
    if not any(url.startswith(prefix) for prefix in allowed_prefixes):
        raise ValidationError(
            f"Invalid Git URL '{url}'. Must start with https:// or git@"
        )

    # Prevent dangerous protocols
    dangerous_protocols = ('file://', 'ftp://', 'ssh://', 'ext::')
    if any(protocol in url.lower() for protocol in dangerous_protocols):
        raise ValidationError(
            f"Dangerous protocol in Git URL '{url}'. Only https:// and git@ allowed."
        )

    # Prevent command injection through URL
    dangerous_chars = [';', '|', '&', '\n', '\r', '`', '$']
    if any(char in url for char in dangerous_chars):
        raise ValidationError(
            f"Git URL contains dangerous characters: {url}"
        )

    # Validate basic URL structure
    if url.startswith('https://'):
        # Basic check for https URLs
        if not re.match(r'^https://[a-zA-Z0-9.-]+/[\w\-./]+\.git$', url):
            raise ValidationError(
                f"Invalid HTTPS Git URL format: {url}"
            )
    elif url.startswith('git@'):
        # Basic check for git@ URLs
        if not re.match(r'^git@[a-zA-Z0-9.-]+:[\w\-./]+\.git$', url):
            raise ValidationError(
                f"Invalid git@ URL format: {url}"
            )

    return url


def sanitize_for_shell(value: str) -> str:
    """
    Sanitize a string for safe use in shell commands.

    Uses shlex.quote() to properly escape shell metacharacters.

    Args:
        value: String to sanitize

    Returns:
        Shell-safe quoted string

    Example:
        ```python
        safe = sanitize_for_shell("hello world")     # 'hello world'
        safe = sanitize_for_shell("rm -rf /")        # 'rm -rf /'
        safe = sanitize_for_shell("file; rm -rf /")  # 'file; rm -rf /'
        ```
    """
    return shlex.quote(str(value))


def sanitize_container_name(name: str) -> str:
    """
    Sanitize Docker container name.

    Docker container names must match: [a-zA-Z0-9][a-zA-Z0-9_.-]+

    Args:
        name: Desired container name

    Returns:
        Sanitized container name

    Raises:
        ValidationError: If name cannot be sanitized

    Example:
        ```python
        name = sanitize_container_name("my-container")  # OK
        name = sanitize_container_name("../../etc")     # Raises ValidationError
        ```
    """
    if not name:
        raise ValidationError("Container name cannot be empty")

    # Docker names: [a-zA-Z0-9][a-zA-Z0-9_.-]+
    if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9_.-]+$', name):
        raise ValidationError(
            f"Invalid container name '{name}'. "
            "Must start with alphanumeric and contain only [a-zA-Z0-9_.-]"
        )

    # Prevent excessive length
    if len(name) > 128:
        raise ValidationError(f"Container name too long (max 128): {len(name)}")

    return name


def sanitize_api_key_for_logging(api_key: str, visible_chars: int = 4) -> str:
    """
    Sanitize API key for safe logging.

    Shows only first few characters, masks the rest.

    Args:
        api_key: API key to sanitize
        visible_chars: Number of characters to show (default: 4)

    Returns:
        Masked API key safe for logging

    Example:
        ```python
        safe = sanitize_api_key_for_logging("ghp_1234567890abcdef")
        # Returns: "ghp_****"

        safe = sanitize_api_key_for_logging("sk-1234567890", visible_chars=3)
        # Returns: "sk-****"
        ```
    """
    if not api_key:
        return "****"

    if len(api_key) <= visible_chars:
        return "****"

    return f"{api_key[:visible_chars]}****"


def validate_port(port: Any) -> int:
    """
    Validate port number.

    Args:
        port: Port number to validate

    Returns:
        Validated port number

    Raises:
        ValidationError: If port is invalid

    Example:
        ```python
        port = validate_port(3000)     # OK
        port = validate_port("3000")   # OK (converts)
        port = validate_port(99999)    # Raises ValidationError
        ```
    """
    try:
        port_num = int(port)
    except (ValueError, TypeError):
        raise ValidationError(f"Invalid port '{port}'. Must be an integer.")

    if port_num < 1 or port_num > 65535:
        raise ValidationError(
            f"Port {port_num} out of range. Must be 1-65535."
        )

    # Warn about privileged ports (< 1024) but don't block
    # (may be running in Docker where this is OK)
    if port_num < 1024:
        import warnings
        warnings.warn(
            f"Port {port_num} is privileged (<1024). May require elevated permissions."
        )

    return port_num


def validate_timeout(timeout: Any) -> float:
    """
    Validate timeout value.

    Args:
        timeout: Timeout in seconds

    Returns:
        Validated timeout as float

    Raises:
        ValidationError: If timeout is invalid

    Example:
        ```python
        timeout = validate_timeout(30.0)    # OK
        timeout = validate_timeout("30")    # OK (converts)
        timeout = validate_timeout(-5)      # Raises ValidationError
        ```
    """
    try:
        timeout_val = float(timeout)
    except (ValueError, TypeError):
        raise ValidationError(f"Invalid timeout '{timeout}'. Must be a number.")

    if timeout_val <= 0:
        raise ValidationError(f"Timeout must be > 0, got {timeout_val}")

    if timeout_val > 3600:
        raise ValidationError(
            f"Timeout too long ({timeout_val}s). Maximum is 3600s (1 hour)."
        )

    return timeout_val


# Export all public functions
__all__ = [
    'ValidationError',
    'validate_sandbox_id',
    'validate_num_agents',
    'validate_git_url',
    'sanitize_for_shell',
    'sanitize_container_name',
    'sanitize_api_key_for_logging',
    'validate_port',
    'validate_timeout',
]
