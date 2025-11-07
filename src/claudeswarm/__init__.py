"""Claude Swarm - Multi-agent coordination system for Claude Code instances.

This package provides a tmux-based coordination system that enables multiple Claude Code
agents to work together on shared projects through:
- Agent discovery and registry management
- Inter-agent messaging via tmux send-keys
- Distributed file locking to prevent conflicts
- Message acknowledgment and retry system
- Real-time monitoring and visibility
- Shared coordination file management
"""

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "discovery",
    "messaging",
    "locking",
    "ack",
    "monitoring",
    "coordination",
    "cli",
    "utils",
]
