"""Project root detection for Claude Swarm.

This module provides utilities for detecting the project root directory
across different deployment scenarios:
- Development: Running from within the repository
- Global install: Running from any directory with CLAUDESWARM_ROOT env var
- Auto-detect: Search for project markers (.git, ACTIVE_AGENTS.json, etc.)
- Explicit: Passing project_root parameter to functions

Priority order:
1. Explicit project_root parameter (if provided)
2. CLAUDESWARM_ROOT environment variable
3. Auto-detect by searching for marker files
4. Current working directory (fallback)
"""

import os
import sys
from pathlib import Path
from typing import Optional

__all__ = [
    "get_project_root",
    "find_project_root",
    "get_active_agents_path",
    "get_messages_log_path",
    "get_locks_dir_path",
]

# Marker files that indicate a project root
PROJECT_MARKERS = [
    ".git",                    # Git repository
    ".claudeswarm.yaml",      # Claude Swarm config
    "ACTIVE_AGENTS.json",     # Active agents registry
    ".agent_locks",           # Lock directory
    "pyproject.toml",         # Python project
    "package.json",           # Node project
]


def find_project_root(start_path: Optional[Path] = None, max_depth: int = 10) -> Optional[Path]:
    """Find project root by searching for marker files.

    Searches upward from start_path looking for common project markers
    like .git, .claudeswarm.yaml, ACTIVE_AGENTS.json, etc.

    Args:
        start_path: Directory to start searching from (default: cwd)
        max_depth: Maximum number of parent directories to check

    Returns:
        Path to project root if found, None otherwise

    Examples:
        >>> # Auto-detect from current directory
        >>> root = find_project_root()

        >>> # Search from specific path
        >>> root = find_project_root(Path('/path/to/subdir'))
    """
    current = (start_path or Path.cwd()).resolve()

    # Search up to max_depth parent directories
    for _ in range(max_depth):
        # Check if any marker files exist in current directory
        for marker in PROJECT_MARKERS:
            marker_path = current / marker
            if marker_path.exists():
                return current

        # Move to parent directory
        parent = current.parent
        if parent == current:  # Reached root of filesystem
            break
        current = parent

    return None


def get_project_root(project_root: Optional[Path] = None) -> Path:
    """Get the project root directory with smart detection.

    This function determines the project root using the following priority:
    1. Explicit project_root parameter (if provided)
    2. CLAUDESWARM_ROOT environment variable
    3. Auto-detect by searching for project markers
    4. Current working directory (fallback)

    Args:
        project_root: Optional explicit project root path

    Returns:
        Path to the project root directory

    Examples:
        >>> # Auto-detect (recommended)
        >>> root = get_project_root()

        >>> # Use environment variable
        >>> os.environ['CLAUDESWARM_ROOT'] = '/path/to/project'
        >>> root = get_project_root()

        >>> # Use explicit path
        >>> root = get_project_root(Path('/specific/project'))
    """
    # Priority 1: Explicit parameter
    if project_root is not None:
        return Path(project_root).resolve()

    # Priority 2: Environment variable
    env_root = os.getenv("CLAUDESWARM_ROOT")
    if env_root:
        return Path(env_root).resolve()

    # Priority 3: Auto-detect by searching for markers
    detected_root = find_project_root()
    if detected_root is not None:
        return detected_root

    # Priority 4: Current working directory (fallback)
    return Path.cwd().resolve()


def get_active_agents_path(project_root: Optional[Path] = None) -> Path:
    """Get the path to the ACTIVE_AGENTS.json file.

    Args:
        project_root: Optional project root path

    Returns:
        Path to ACTIVE_AGENTS.json
    """
    return get_project_root(project_root) / "ACTIVE_AGENTS.json"


def get_messages_log_path(project_root: Optional[Path] = None) -> Path:
    """Get the path to the agent_messages.log file.

    Args:
        project_root: Optional project root path

    Returns:
        Path to agent_messages.log
    """
    return get_project_root(project_root) / "agent_messages.log"


def get_locks_dir_path(project_root: Optional[Path] = None) -> Path:
    """Get the path to the .agent_locks directory.

    Args:
        project_root: Optional project root path

    Returns:
        Path to .agent_locks directory
    """
    return get_project_root(project_root) / ".agent_locks"
