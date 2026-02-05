"""Terminal backend abstraction for Claude Swarm.

This module provides a backend abstraction layer that enables claude-swarm
to work with different terminal environments:
- TmuxBackend: Full tmux integration (existing behavior)
- ProcessBackend: OS-level process scanning for any terminal (Ghostty, iTerm2, etc.)

Auto-detection picks the right backend based on environment variables and config.
"""

from __future__ import annotations

import os
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from .logging_config import get_logger

logger = get_logger(__name__)

__all__ = [
    "TerminalBackend",
    "AgentInfo",
    "detect_backend",
    "get_backend",
    "reset_backend",
]


@dataclass
class AgentInfo:
    """Backend-agnostic agent information.

    This is the common data structure returned by all backend implementations
    when discovering agents. It maps to the discovery.Agent dataclass but is
    independent of any specific terminal backend.

    Attributes:
        agent_id: Unique agent identifier (e.g., "agent-0")
        pid: Process ID of the Claude Code instance
        identifier: Backend-specific identifier (tmux pane ID, TTY path, etc.)
        session_name: Terminal session name (tmux session, terminal app name)
        status: Current status ("active", "stale", "dead")
        cwd: Current working directory of the agent process
        metadata: Additional backend-specific metadata
    """

    agent_id: str
    pid: int
    identifier: str
    session_name: str
    status: str = "active"
    cwd: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class TerminalBackend(ABC):
    """Abstract base class for terminal backends.

    Defines the interface that all terminal backend implementations must support.
    Each backend handles agent discovery, messaging, and identity in its own way.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the backend name (e.g., 'tmux', 'process')."""
        ...

    @abstractmethod
    def discover_agents(self, project_root: str | None = None) -> list[AgentInfo]:
        """Discover active Claude Code agents.

        Args:
            project_root: Optional project root to filter agents by.

        Returns:
            List of AgentInfo for each discovered agent.
        """
        ...

    @abstractmethod
    def send_message(self, target_identifier: str, message: str) -> bool:
        """Send a message to an agent via the backend's native mechanism.

        For tmux, this uses send-keys. For process backend, this returns False
        (file-based messaging is used instead via the existing hooks system).

        Args:
            target_identifier: Backend-specific target (pane ID, TTY path, etc.)
            message: Formatted message string to deliver.

        Returns:
            True if real-time delivery succeeded, False if file-based fallback needed.
        """
        ...

    @abstractmethod
    def verify_agent(self, identifier: str) -> bool:
        """Verify that an agent is still alive/reachable.

        Args:
            identifier: Backend-specific agent identifier.

        Returns:
            True if agent is verified as reachable.
        """
        ...

    @abstractmethod
    def get_current_agent_identifier(self) -> str | None:
        """Get the identifier for the current agent (this process).

        For tmux, returns TMUX_PANE. For process backend, returns TTY path.

        Returns:
            Backend-specific identifier string, or None if not determinable.
        """
        ...

    def create_monitoring_pane(self) -> str | None:
        """Create a dedicated monitoring pane/window.

        Optional method. Returns None if the backend doesn't support
        creating new terminal panes (e.g., ProcessBackend).

        Returns:
            Pane/window identifier if created, None otherwise.
        """
        return None


def detect_backend() -> TerminalBackend:
    """Auto-detect and instantiate the appropriate terminal backend.

    Detection order:
    1. CLAUDESWARM_BACKEND env var override ("tmux" or "process")
    2. Config file backend.provider if not "auto"
    3. TMUX env var set + tmux running -> TmuxBackend
    4. Default -> ProcessBackend

    Returns:
        Instantiated TerminalBackend implementation.
    """
    # 1. Environment variable override
    env_backend = os.environ.get("CLAUDESWARM_BACKEND", "").lower().strip()
    if env_backend:
        if env_backend == "tmux":
            logger.info("Using TmuxBackend (CLAUDESWARM_BACKEND env var)")
            from .tmux_backend import TmuxBackend

            return TmuxBackend()
        elif env_backend == "process":
            logger.info("Using ProcessBackend (CLAUDESWARM_BACKEND env var)")
            from .process_backend import ProcessBackend

            return ProcessBackend()
        else:
            # Truncate to prevent log injection with very long values
            safe_value = env_backend[:30]
            logger.warning(
                f"Unknown CLAUDESWARM_BACKEND value '{safe_value}', falling back to auto-detection"
            )

    # 2. Config file override
    try:
        from .config import get_config

        config = get_config()
        if hasattr(config, "backend") and config.backend is not None:
            provider = config.backend.provider.lower() if config.backend.provider else None
            if provider and provider != "auto":
                if provider == "tmux":
                    logger.info("Using TmuxBackend (config file)")
                    from .tmux_backend import TmuxBackend

                    return TmuxBackend()
                elif provider == "process":
                    logger.info("Using ProcessBackend (config file)")
                    from .process_backend import ProcessBackend

                    return ProcessBackend()
                else:
                    logger.warning(
                        f"Unknown backend provider '{provider[:30]}' in config, "
                        f"falling back to auto-detection"
                    )
    except (FileNotFoundError, ImportError):
        # Config not available yet, continue with auto-detection
        pass
    except Exception as e:
        logger.debug(f"Config loading failed during backend detection: {e}")

    # 3. Auto-detect: check for tmux (either TMUX or TMUX_PANE env var)
    if os.environ.get("TMUX") or os.environ.get("TMUX_PANE"):
        logger.info("Using TmuxBackend (tmux env var detected)")
        from .tmux_backend import TmuxBackend

        return TmuxBackend()

    # 4. Default: process-based backend
    logger.info("Using ProcessBackend (default - no tmux detected)")
    from .process_backend import ProcessBackend

    return ProcessBackend()


# Singleton management
_backend_instance: TerminalBackend | None = None
_backend_lock = threading.Lock()


def get_backend() -> TerminalBackend:
    """Get the singleton backend instance.

    Thread-safe lazy initialization. Uses detect_backend() on first call.

    Returns:
        The singleton TerminalBackend instance.
    """
    global _backend_instance

    if _backend_instance is None:
        with _backend_lock:
            if _backend_instance is None:
                _backend_instance = detect_backend()

    return _backend_instance


def reset_backend() -> None:
    """Reset the singleton backend instance.

    Useful for testing or when the environment changes.
    """
    global _backend_instance

    with _backend_lock:
        _backend_instance = None
