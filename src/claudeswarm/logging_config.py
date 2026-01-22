"""Centralized logging configuration for Claude Swarm.

This module provides structured logging setup to ensure consistent
logging format across all modules. It handles:
- Configurable log levels
- Custom format strings
- Optional file logging
- Third-party library noise reduction
- Per-module logger creation

Usage:
    # In main entry point (cli.py):
    from .logging_config import setup_logging
    setup_logging(level="INFO")

    # In any module:
    from .logging_config import get_logger
    logger = get_logger(__name__)
    logger.info("Operation completed successfully")
"""

from __future__ import annotations

import logging
import sys
from typing import Optional

__all__ = [
    "setup_logging",
    "get_logger",
]


def setup_logging(
    level: str = "INFO",
    format_string: Optional[str] = None,
    log_file: Optional[str] = None
) -> None:
    """Configure logging for claude-swarm.

    This function should be called once at application startup to
    configure the logging system for all claudeswarm modules.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_string: Custom format string (default includes timestamp, name, level, message)
        log_file: Optional file path to write logs to (in addition to stderr)

    Example:
        >>> setup_logging(level="DEBUG", log_file="/tmp/claudeswarm.log")
        >>> # All loggers will now log at DEBUG level to both stderr and file

    Note:
        - Logs are written to stderr by default (not stdout) to avoid mixing with program output
        - Third-party library loggers (uvicorn, httpx) are set to WARNING to reduce noise
        - File logging is appended (mode='a') if log_file is specified
    """
    if format_string is None:
        format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    handlers = [logging.StreamHandler(sys.stderr)]

    if log_file:
        handlers.append(logging.FileHandler(log_file, mode='a'))

    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=format_string,
        handlers=handlers,
        force=True  # Override any existing configuration
    )

    # Set specific loggers for claudeswarm modules
    logging.getLogger("claudeswarm").setLevel(getattr(logging, level.upper()))

    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger for the given module name.

    This function should be called at module level to create a logger
    for that module. The logger name will be prefixed with "claudeswarm."
    unless it already starts with "claudeswarm".

    Args:
        name: Module name (typically __name__ from the calling module)

    Returns:
        A configured logger instance for the module

    Example:
        >>> # In messaging.py:
        >>> logger = get_logger(__name__)
        >>> logger.info("Message sent successfully")
        >>> # Output: 2025-01-22 10:30:45 - claudeswarm.messaging - INFO - Message sent successfully

    Note:
        - Use __name__ as the argument to get proper module hierarchy
        - Loggers inherit settings from parent loggers (e.g., claudeswarm.messaging inherits from claudeswarm)
    """
    # Strip 'claudeswarm.' prefix if already present to avoid duplication
    if name.startswith("claudeswarm."):
        name = name[len("claudeswarm."):]

    # Don't add prefix if it's already "claudeswarm"
    if name == "claudeswarm":
        return logging.getLogger(name)

    return logging.getLogger(f"claudeswarm.{name}")
