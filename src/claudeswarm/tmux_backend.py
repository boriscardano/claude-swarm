"""Tmux terminal backend for Claude Swarm.

This module wraps existing tmux-based functionality from discovery.py and
messaging.py into the TerminalBackend interface. It provides the same behavior
as the original tmux integration but through the backend abstraction.
"""

from __future__ import annotations

import os

from .backend import AgentInfo, TerminalBackend
from .logging_config import get_logger

logger = get_logger(__name__)

__all__ = ["TmuxBackend"]


class TmuxBackend(TerminalBackend):
    """Tmux-based terminal backend.

    Uses tmux commands for agent discovery, messaging via send-keys,
    and pane-based identity. This is the original claude-swarm behavior
    wrapped in the backend abstraction.
    """

    @property
    def name(self) -> str:
        return "tmux"

    def discover_agents(self, project_root: str | None = None) -> list[AgentInfo]:
        """Discover agents by scanning tmux panes for Claude Code processes.

        Delegates to the existing _parse_tmux_panes() and process detection
        helpers in the discovery module.

        Args:
            project_root: Optional project root to filter agents by.

        Returns:
            List of AgentInfo for discovered agents.
        """
        from .discovery import (
            _get_process_cwd,
            _is_claude_code_process,
            _parse_tmux_panes,
        )

        try:
            panes = _parse_tmux_panes()
        except Exception as e:
            logger.error(f"Failed to parse tmux panes: {e}")
            return []

        agents = []
        for pane in panes:
            if not _is_claude_code_process(pane["command"], pane["pid"]):
                continue

            # Filter by project root if specified
            if project_root:
                cwd = _get_process_cwd(pane["pid"])
                if cwd and not cwd.startswith(project_root):
                    continue

            identifier = pane.get("tmux_pane_id") or pane["pane_index"]
            cwd = _get_process_cwd(pane["pid"])

            agents.append(
                AgentInfo(
                    agent_id="",  # Assigned by discovery module
                    pid=pane["pid"],
                    identifier=identifier,
                    session_name=pane["session_name"],
                    status="active",
                    cwd=cwd,
                    metadata={
                        "pane_index": pane["pane_index"],
                        "tmux_pane_id": pane.get("tmux_pane_id"),
                        "command": pane.get("command"),
                    },
                )
            )

        return agents

    def send_message(self, target_identifier: str, message: str) -> bool:
        """Send a message to an agent via tmux send-keys.

        Args:
            target_identifier: Tmux pane ID (e.g., "%5" or "session:0.1").
            message: Formatted message string.

        Returns:
            True if delivery succeeded.
        """
        from .messaging import TmuxMessageDelivery

        try:
            return TmuxMessageDelivery.send_to_pane(target_identifier, message)
        except Exception as e:
            logger.debug(f"Tmux send_message failed: {e}")
            return False

    def verify_agent(self, identifier: str) -> bool:
        """Verify a tmux pane exists.

        Args:
            identifier: Tmux pane ID to verify.

        Returns:
            True if pane exists.
        """
        from .messaging import TmuxMessageDelivery

        return TmuxMessageDelivery.verify_pane_exists(identifier)

    def get_current_agent_identifier(self) -> str | None:
        """Get the current tmux pane ID from TMUX_PANE environment variable.

        Returns:
            TMUX_PANE value, or None if not in tmux.
        """
        return os.environ.get("TMUX_PANE")

    def create_monitoring_pane(self) -> str | None:
        """Create a dedicated tmux monitoring pane.

        Returns:
            Pane ID if created, None on failure.
        """
        from .monitoring import create_tmux_monitoring_pane

        return create_tmux_monitoring_pane()
